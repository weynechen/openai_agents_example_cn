"""
Dog Agent with Gradio UI - Digital life simulation of a dog.

Features:
1. Interactive Mode: Responds to owner's commands via Gradio chat interface
2. Autonomous Mode: Autonomous behaviors triggered by timer when no interaction
3. Real-time state monitoring
"""
# import dump_promt

import dotenv
import os
import asyncio
import time
import threading
from queue import Queue
from dataclasses import dataclass
from typing import Callable

dotenv.load_dotenv()

import gradio as gr
from agents import Agent, Runner, SQLiteSession
from agents.extensions.models.litellm_model import LitellmModel
from dog_state import DogStateManager
from dog_behaviors import get_all_behavior_tools, set_state_manager, set_behavior_callback, set_behavior_queue, set_video_callback


# Video directory path
VIDEO_DIR = "/home/ubuntu/project/test/openai_agents/video"
DEFAULT_VIDEO = f"{VIDEO_DIR}/default.mp4"


@dataclass
class BehaviorTask:
    """Behavior task in queue"""
    behavior_type: str          # "long_term" or "instant"
    action: Callable           # The actual function to execute
    description: str           # Description for display
    estimated_duration: float  # Estimated duration in virtual minutes (0 for instant)
    behavior_name: str = None  # Function name for video matching


class DogAgentGradio:
    """Dog agent with Gradio UI"""
    
    def __init__(self, session_id: str = "dog_session_gradio", time_scale: float = 1.0):
        print("[INIT] Initializing Dog Agent...")
        
        # Initialize state manager with time scale
        self.state_manager = DogStateManager(time_scale=time_scale)
        set_state_manager(self.state_manager)
        
        # Behavior execution queue
        self.behavior_queue = Queue()
        self.queue_executor_task = None
        self.is_executing_behavior = False
        self.current_executing_behavior = None
        
        # Video playback state
        self.current_video_path = DEFAULT_VIDEO
        self.video_update_timestamp = time.time()
        self.last_video_check = time.time()
        self.last_returned_video = None  # Track last returned video to detect changes
        
        # Chat history (shared between autonomous and interactive modes)
        self.chat_history = []
        
        # Track behaviors executed in current cycle (for display)
        self.current_cycle_behaviors = []
        
        # Set behavior callback to capture tool outputs
        set_behavior_callback(self._on_behavior_executed)
        
        # Set behavior queue for long-term behaviors
        set_behavior_queue(self.behavior_queue)
        
        # Set video callback to handle video playback
        set_video_callback(self._on_video_request)
        
        # Initialize session
        self.session = SQLiteSession(session_id)
        
        # Mode tracking
        self.mode = "autonomous"  # autonomous or interactive
        self.last_interaction_time = time.time()
        self.autonomous_interval = 15  # seconds before triggering autonomous mode
        
        # Create agent
        self.agent = Agent(
            name="Dog",
            instructions=self._get_instructions(),
            tools=get_all_behavior_tools(),
            model=LitellmModel(
                model="deepseek/deepseek-chat",
                api_key=os.getenv("DEEPSEEK_API_KEY")
            )
        )
        
        # Background task flag
        self.running = True
        self.autonomous_task = None
        
        print("[INIT] Dog Agent initialized successfully!")
    
    def _get_instructions(self) -> str:
        """Get dynamic instructions based on mode"""
        base = """你现在是一条狗。你可以使用可用的工具来执行各种行为。

重要规则：
1. 你必须使用工具来执行动作 - 调用相应的工具函数
2. 不要只用文字描述动作，你必须调用工具
3. 你可以按顺序调用多个工具来创建自然的行为组合
4. 保持回复简洁 - 专注于行动，不要长篇解释
5. ⭐ 所有行为都有 duration_seconds 参数，根据实际情况设置合适的时间

可用行为类别 (所有行为都需要 duration_seconds 参数):
- 生理类: stretch(3-10s), yawn(2-5s), drink_water(300-600s), eat_food(300-900s), lick_fur(10-60s), sleep(1800-14400s)
- 社交类: wag_tail(2-10s), nuzzle_owner(5-20s), lick_hand(3-15s), follow_owner(5-30s), look_up_at_owner(2-10s)
- 探索类: sniff_ground(5-30s), walk_in_circles(10-60s), paw_at_object(5-30s), look_out_window(30-300s), chase_light(20-120s)
- 情绪类: bark(2-15s), growl(3-20s), pin_ears_back(2-15s), tuck_tail(5-30s), jump_excitedly(5-30s)
- 训练类: sit(10-120s), lie_down(30-300s), shake_paw(3-10s), roll_over(5-15s), play_dead(5-30s), fetch_object(30-180s)
- 特殊类: scratch_itch(5-20s), sneeze(1-3s), shake_body(3-8s), snore(30-300s), dream_twitch(10-120s)

⏱️ 时间设置指南（单位：秒）:

【长时行为】- 基于状态调整时间
• sleep: 根据疲劳程度
  - 筋疲力尽 (>80): 10800-14400s (3-4小时)
  - 累了 (>50): 7200s (2小时)
  - 有点累: 1800-3600s (0.5-1小时)
  
• eat_food: 根据饥饿程度
  - 非常饿 (>80): 900s (15分钟)
  - 饿了 (>50): 720s (12分钟)
  - 有点饿: 420s (7分钟)
  
• drink_water: 根据口渴程度
  - 非常渴 (>80): 600s (10分钟)
  - 渴了 (>50): 480s (8分钟)
  - 有点渴: 300s (5分钟)

【快速行为】- 根据情境调整时间
• 瞬间动作 (2-5s): yawn, sneeze, wag_tail, look_up
• 短动作 (5-15s): stretch, bark, shake_paw, paw_at_object
• 中等动作 (15-60s): lick_fur, walk_in_circles, fetch_object, sit
• 持续动作 (60-300s): look_out_window, lie_down, snore

"""
        
        if self.mode == "autonomous":
            return base + """模式：自主模式
你正在根据内部需求独立行动。

🎯 行为规划系统:
- 你可以一次规划多个行为，它们会按顺序执行
- 长时行为 (sleep, eat_food, drink_water) 会加入执行队列
- 快速行为会立即执行
- 可以组合快速和长时行为，如: stretch(), drink_water(), walk_in_circles()

根据你当前的状态决定做什么：
- 如果饿了 (>70): eat_food(duration_seconds=根据饥饿程度)
- 如果渴了 (>70): drink_water(duration_seconds=根据口渴程度)
- 如果累了 (>80): sleep(duration_seconds=根据疲劳程度)
- 如果无聊 (>70): 探索或玩耍 (sniff, chase_light, paw_at_object, 等)
- 如果有多个需求: 可以规划多个行为
- 否则: 执行日常行为 (stretch, yawn, walk_in_circles, 等)

💡 示例规划:
- 非常饿又渴 (饥饿85, 口渴75): 
  eat_food(duration_seconds=900), drink_water(duration_seconds=600)
  
- 有点饿很累 (饥饿55, 疲劳82): 
  eat_food(duration_seconds=600), sleep(duration_seconds=12000)
  
- 刚睡醒想玩 (疲劳20, 无聊70): 
  stretch(duration_seconds=5), yawn(duration_seconds=3), chase_light(duration_seconds=60)
  
- 无聊想探索:
  sniff_ground(duration_seconds=15), walk_in_circles(duration_seconds=20), look_out_window(duration_seconds=120)"""
        else:  # interactive
            return base + """模式：交互模式
你正在回应主人的指令和互动。

例子：
主人: "过来"
-> 你: look_up_at_owner(duration_seconds=3), wag_tail(duration_seconds=5), follow_owner(duration_seconds=10)

主人: "坐下"
-> 你: sit(duration_seconds=30)  # 乖乖坐着等待

主人: "好狗狗！" (抚摸你)
-> 你: wag_tail(duration_seconds=8), lick_hand(duration_seconds=10), jump_excitedly(duration_seconds=15)

主人: "去睡觉吧"
-> 你: 根据疲劳程度决定睡眠时间
  如果很累: yawn(duration_seconds=3), sleep(duration_seconds=10800)
  如果不太累: sleep(duration_seconds=3600)

主人: "去吃饭"
-> 你: 根据饥饿程度决定进食时间
  如果很饿: eat_food(duration_seconds=900)
  如果不太饿: eat_food(duration_seconds=600)

主人: "陪我玩会儿"
-> 你: jump_excitedly(duration_seconds=10), fetch_object(duration_seconds=90), wag_tail(duration_seconds=8)

⭐ 记住：每个行为都要指定 duration_seconds，时间长短要符合狗狗的实际情况！"""
    
    async def _run_autonomous_cycle(self):
        """Run one autonomous behavior cycle"""
        print("\n" + "="*60)
        print("[AUTONOMOUS] Dog is acting independently...")
        print("="*60)
        
        # Clear previous cycle behaviors
        self.current_cycle_behaviors = []
        
        # Update instructions for autonomous mode
        self.mode = "autonomous"
        self.agent.instructions = self._get_instructions()
        
        # Get state description
        state_desc = self.state_manager.get_state_description()
        prompt = f"{state_desc}\n\n你现在要做什么？"
        
        print(f"[PROMPT] {prompt}")
        
        # Run agent
        result = await Runner.run(
            self.agent,
            prompt,
            session=self.session
        )
        
        output = result.final_output
        print(f"[OUTPUT] [自主行为] {output}")
        
        # Build display message from behaviors and/or output
        display_parts = []
        if self.current_cycle_behaviors:
            display_parts.append("执行动作: " + "、".join(self.current_cycle_behaviors))
        if output and output.strip():
            display_parts.append(output)
        
        display_message = "\n".join(display_parts) if display_parts else "🐾 (观察中...)"
        
        # Add to chat history
        self.chat_history.append({
            "role": "assistant",
            "content": f"🤖 [自主行为]\n{display_message}"
        })
        
        return output
    
    async def _run_interactive_cycle(self, user_input: str):
        """Run interactive response to user input"""
        print("\n" + "="*60)
        print(f"[INTERACTIVE] Responding to owner: {user_input}")
        print("="*60)
        
        # Clear previous cycle behaviors
        self.current_cycle_behaviors = []
        
        # Update instructions for interactive mode
        self.mode = "interactive"
        self.agent.instructions = self._get_instructions()
        
        # Get state description
        state_desc = self.state_manager.get_state_description()
        prompt = f"{state_desc}\n\n主人的动作/指令: {user_input}"
        
        print(f"[PROMPT] {prompt}")
        
        # Run agent
        result = await Runner.run(
            self.agent,
            prompt,
            session=self.session
        )
        
        output = result.final_output
        print(f"[OUTPUT] {output}")
        
        # Build display message from behaviors and/or output
        display_parts = []
        if self.current_cycle_behaviors:
            display_parts.append("🐾 " + "、".join(self.current_cycle_behaviors))
        if output and output.strip():
            display_parts.append(output)
        
        return "\n".join(display_parts) if display_parts else ""
    
    def _on_behavior_executed(self, behavior: str):
        """Callback when a behavior tool is executed"""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        behavior_type = "🤖 自主" if self.mode == "autonomous" else "👤 交互"
        print(f"[BEHAVIOR_EXECUTED] {timestamp} | {behavior_type} | {behavior}")
        
        # Track behavior for display in chat
        self.current_cycle_behaviors.append(behavior)
    
    def _on_video_request(self, behavior_name: str) -> str:
        """Callback when a behavior requests video playback
        
        Args:
            behavior_name: Name of the behavior function (e.g., "sit", "shake_paw")
        
        Returns:
            Path to the video file
        """
        video_path = f"{VIDEO_DIR}/{behavior_name}.mp4"
        
        # Check if video file exists
        if os.path.exists(video_path):
            self.current_video_path = video_path
            print(f"[VIDEO] 🎬 Playing: {behavior_name}.mp4")
        else:
            self.current_video_path = DEFAULT_VIDEO
            print(f"[VIDEO] ⚠️ Video not found for '{behavior_name}', playing default.mp4")
        
        # Update timestamp to trigger UI refresh
        self.video_update_timestamp = time.time()
        
        return self.current_video_path
    
    def get_current_video(self) -> str:
        """Get current video path for UI update
        
        Returns:
            Current video file path
        """
        # Check if video has changed
        if self.current_video_path != self.last_returned_video:
            self.last_returned_video = self.current_video_path
            print(f"[VIDEO_UPDATE] Switching to: {os.path.basename(self.current_video_path)}")
        
        # Return the video file path directly
        # Gradio Video component will handle the display
        return self.current_video_path
    
    def set_time_scale(self, scale: float):
        """Update time scale"""
        self.state_manager.time_scale = scale
        print(f"[TIME_SCALE] Updated to {scale}x (1 second = {scale} virtual minutes)")
        return f"时间加速已设置为 {scale}x"
    
    async def autonomous_behavior_loop(self):
        """Background loop for autonomous behavior"""
        print("[BACKGROUND] Autonomous behavior loop started")
        
        while self.running:
            await asyncio.sleep(3)  # Check every 3 seconds
            
            # First check if dog is busy with long-term behavior
            if self.state_manager.is_busy():
                progress = self.state_manager.get_behavior_progress()
                print(f"[AUTONOMOUS] Dog is busy with {progress['description']}, "
                      f"skipping autonomous cycle (progress: {progress['progress_percent']:.1f}%)")
                continue
            
            # Check if a behavior just completed - trigger immediate autonomous action
            # But NOT if we're in interactive mode (user is actively interacting)
            time_since_last = time.time() - self.last_interaction_time
            if self.state_manager.check_and_clear_completion_flag():
                # Only trigger autonomous action if no recent interaction
                if time_since_last >= self.autonomous_interval:
                    print(f"[TRIGGER] Behavior just completed, triggering autonomous action")
                    await self._run_autonomous_cycle()
                    self.last_interaction_time = time.time()
                else:
                    print(f"[TRIGGER] Behavior completed but user recently interacted ({time_since_last:.1f}s ago), skipping autonomous trigger")
                continue
            
            # Check if it's time for autonomous behavior
            time_since_last = time.time() - self.last_interaction_time
            
            if time_since_last >= self.autonomous_interval:
                print(f"[TRIGGER] {time_since_last:.1f}s since last interaction, triggering autonomous mode")
                
                # Run autonomous cycle
                await self._run_autonomous_cycle()
                
                # Reset timer
                self.last_interaction_time = time.time()
    
    async def behavior_queue_executor(self):
        """Execute behaviors from queue sequentially"""
        print("[EXECUTOR] Behavior queue executor started")
        
        while self.running:
            try:
                # Check if there's a task in queue
                if not self.behavior_queue.empty():
                    task = self.behavior_queue.get()
                    self.is_executing_behavior = True
                    self.current_executing_behavior = task.description
                    
                    print(f"[EXECUTOR] Starting execution: {task.description}")
                    
                    # Trigger video update when actually starting execution
                    if task.behavior_name:
                        self._on_video_request(task.behavior_name)
                    
                    # Execute the action
                    try:
                        result = task.action()
                        print(f"[EXECUTOR] Action result: {task.description} -> {result}")
                        
                        # If this is a long-term behavior, wait for it to complete
                        if task.behavior_type == "long_term":
                            # Check if the behavior was successfully started
                            if not result.startswith("狗狗正在"):
                                print(f"[EXECUTOR] Waiting for long-term behavior '{task.description}' to complete...")
                                # Wait until the behavior is no longer busy
                                while self.state_manager.is_busy() and self.running:
                                    await asyncio.sleep(1)
                                print(f"[EXECUTOR] Long-term behavior '{task.description}' completed!")
                            else:
                                print(f"[EXECUTOR] Long-term behavior '{task.description}' could not start: {result}")
                        
                        # If this was triggered in interactive mode, reset the timer
                        # to give user more time before autonomous mode kicks in
                        if self.mode == "interactive":
                            self.last_interaction_time = time.time()
                            print(f"[EXECUTOR] Interactive behavior completed, timer reset")
                        
                    except Exception as e:
                        print(f"[EXECUTOR] Error executing {task.description}: {e}")
                    
                    self.is_executing_behavior = False
                    self.current_executing_behavior = None
                    self.behavior_queue.task_done()
                else:
                    # No task, sleep briefly
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                print(f"[EXECUTOR] Error in queue executor: {e}")
                await asyncio.sleep(1)
    
    def start_autonomous_task(self):
        """Start the autonomous behavior background task"""
        if self.autonomous_task is None:
            loop = asyncio.new_event_loop()
            
            def run_loop():
                asyncio.set_event_loop(loop)
                # Run both autonomous behavior loop and queue executor
                loop.run_until_complete(asyncio.gather(
                    self.autonomous_behavior_loop(),
                    self.behavior_queue_executor()
                ))
            
            self.autonomous_task = threading.Thread(target=run_loop, daemon=True)
            self.autonomous_task.start()
            print("[TASK] Autonomous task and queue executor started in background")
    
    def stop(self):
        """Stop the agent"""
        print("[STOP] Stopping Dog Agent...")
        self.running = False
        self.state_manager.close()
    
    def create_ui(self):
        """Create Gradio UI"""
        with gr.Blocks(title="🐕 狗狗智能体", theme=gr.themes.Soft()) as demo:
            gr.Markdown("# 🐕 狗狗智能体 - 数字生命模拟")
            gr.Markdown("和你的虚拟狗狗互动！它会根据你的指令做出反应，也会在无聊时自己做些事情。")
            
            # Add a timer for auto-refresh (ticks every 1 second for video updates)
            timer = gr.Timer(value=1, active=True)
            
            # Video display for dog behaviors
            dog_video = gr.Video(
                label="🎬 狗狗动作视频",
                value=DEFAULT_VIDEO,
                autoplay=True,
                loop=True,
                height=400
            )
            
            msg = gr.Textbox(
                label="输入指令 (按回车发送)",
                placeholder="试试说：'过来'、'坐下'、'好狗狗'、'去捡球'..."
            )
            
            # Chat history display
            chatbot = gr.Chatbot(
                label="对话记录",
                height=300,
                type="messages"
            )
            
            # Interactive function
            async def handle_user_input(user_message):
                """Handle user input and get dog's response"""
                if not user_message.strip():
                    return self.chat_history, ""
                
                # Add user message to history
                self.chat_history.append({"role": "user", "content": user_message})
                
                # Reset interaction timer - mark that we're in interactive session
                self.last_interaction_time = time.time()
                
                # Run interactive cycle
                response = await self._run_interactive_cycle(user_message)
                
                # Add dog's response to history
                # If response is empty, agent only executed tools without text output
                if response and response.strip():
                    display_response = response
                else:
                    display_response = "🐾 (执行动作中...)"
                
                self.chat_history.append({"role": "assistant", "content": display_response})
                
                # Reset timer again after interaction completes to prevent immediate autonomous mode
                # Give user time to send next command
                self.last_interaction_time = time.time()
                
                return self.chat_history, ""
            
            # Bind enter key to send message
            msg.submit(
                handle_user_input,
                inputs=[msg],
                outputs=[chatbot, msg]
            )

            with gr.Accordion("⚙️ 时间加速设置", open=False):
                gr.Markdown("""
                调整虚拟时间流逝速度：
                - **1x**: 真实时间（1秒 = 1秒）
                - **60x**: 1秒 = 1分钟（推荐）
                - **120x**: 1秒 = 2分钟
                - **360x**: 1秒 = 6分钟（快速演示）
                """)
                time_scale_slider = gr.Slider(
                    minimum=1,
                    maximum=360,
                    value=self.state_manager.time_scale,
                    step=1,
                    label="时间加速倍数",
                    interactive=True
                )
                time_scale_info = gr.Textbox(
                    value=f"当前: {self.state_manager.time_scale}x",
                    label="当前设置",
                    interactive=False
                )
                time_scale_preset = gr.Radio(
                    choices=["1x 真实", "60x 标准", "120x 快速", "360x 演示"],
                    value="60x 标准" if self.state_manager.time_scale == 60 else "1x 真实",
                    label="预设",
                    interactive=True
                )

            
            # Time scale controls
            def update_time_scale_slider(value):
                self.set_time_scale(value)
                return f"当前: {value}x"
            
            def update_time_scale_preset(choice):
                scale_map = {
                    "1x 真实": 1,
                    "60x 标准": 60,
                    "120x 快速": 120,
                    "360x 演示": 360
                }
                scale = scale_map.get(choice, 60)
                self.set_time_scale(scale)
                return scale, f"当前: {scale}x"
            
            time_scale_slider.change(
                update_time_scale_slider,
                inputs=time_scale_slider,
                outputs=time_scale_info
            )
            
            time_scale_preset.change(
                update_time_scale_preset,
                inputs=time_scale_preset,
                outputs=[time_scale_slider, time_scale_info]
            )
            
            # Timer update function (updates both video and chat)
            def update_ui():
                """Update video display and chat history"""
                video_path = self.get_current_video()
                # Force update to trigger autoplay when video changes
                return gr.update(value=video_path), self.chat_history
            
            # Bind timer to update video and chat
            timer.tick(
                update_ui,
                outputs=[dog_video, chatbot]
            )
        
        return demo


def main():
    """Main entry point"""
    print("="*60)
    print("🐕 Starting Dog Agent with Gradio UI")
    print("="*60)
    
    # Create agent with default time scale (60x for demonstration)
    # 60x means: 1 real second = 1 virtual minute
    # So 8 virtual minutes = 8 real seconds
    default_time_scale = 30.0
    dog_agent = DogAgentGradio(time_scale=default_time_scale)
    print(f"[TIME_SCALE] Default time scale: {default_time_scale}x (1 second = {default_time_scale} virtual minutes)")
    print(f"[TIME_SCALE] Example: 8 min sleep = {8/default_time_scale:.1f} real seconds")
    
    # Start autonomous behavior task
    dog_agent.start_autonomous_task()
    
    # Create and launch UI
    demo = dog_agent.create_ui()
    
    try:
        demo.launch(
            server_name="0.0.0.0",
            server_port=7860,
            share=False
        )
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Shutting down...")
    finally:
        dog_agent.stop()


if __name__ == "__main__":
    main()

