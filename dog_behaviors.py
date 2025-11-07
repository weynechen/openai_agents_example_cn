"""
Dog behavior tools - 32 behaviors across 6 categories.
Each behavior is a function_tool that modifies dog state.
"""

from agents import function_tool
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dog_state import DogStateManager

# Global state manager (will be set by main program)
state_manager: 'DogStateManager' = None
behavior_callback = None  # Callback function to report behaviors
behavior_queue = None  # Queue for behavior execution
video_callback = None  # Callback function to request video playback


def set_state_manager(manager: 'DogStateManager'):
    """Set the global state manager"""
    global state_manager
    state_manager = manager


def set_behavior_callback(callback):
    """Set callback function to report behaviors to UI"""
    global behavior_callback
    behavior_callback = callback


def set_behavior_queue(queue):
    """Set behavior execution queue"""
    global behavior_queue
    behavior_queue = queue


def set_video_callback(callback):
    """Set callback function to request video playback"""
    global video_callback
    video_callback = callback


def _log_behavior(message: str, behavior_display: str = None) -> str:
    """Log behavior action to console and report to UI
    
    Args:
        message: Full message for console and LLM
        behavior_display: Simplified display for behavior history (if None, use message)
    """
    print(f"  🐾 {message}")
    
    # Call callback to add to behavior history with simplified display
    if behavior_callback:
        behavior_callback(behavior_display if behavior_display else message)
    
    return message


def _queue_behavior(behavior_type: str, duration: float, description: str, action_func, message: str, behavior_name: str = None):
    """Add any behavior to execution queue
    
    Args:
        behavior_type: Type of behavior ("instant" or "long_term")
        duration: Duration in minutes
        description: Display description (shown in behavior history)
        action_func: Function to execute (optional, for instant behaviors)
        message: Message to return to LLM
        behavior_name: Function name for video matching (if None, extracted from call stack)
    """
    # Get behavior function name for video playback
    if behavior_name is None:
        import inspect
        frame = inspect.currentframe().f_back
        behavior_name = frame.f_code.co_name
    
    if behavior_queue is None:
        # Fallback: execute immediately
        # Trigger video callback for immediate execution
        if video_callback:
            video_callback(behavior_name)
        if action_func:
            action_func()
        # For immediate execution, show the actual behavior
        return _log_behavior(message, behavior_display=description)
    
    # Create action to execute later
    def execute_behavior():
        if action_func:
            action_func()
        return message
    
    # Add to queue (video will be triggered when executor starts this task)
    from dog_agent_gradio import BehaviorTask
    task = BehaviorTask(
        behavior_type=behavior_type,
        action=execute_behavior,
        description=description,
        estimated_duration=duration,
        behavior_name=behavior_name  # Store for later video update
    )
    behavior_queue.put(task)
    
    # Log to console with details, but show only behavior name in history
    log_message = f"✓ 计划{description} ({duration:.1f}分钟) - 已加入队列"
    print(f"  🐾 {log_message}")
    
    # Add to behavior history with just the behavior description
    if behavior_callback:
        behavior_callback(description)
    
    # Return simple confirmation to LLM
    return f"✓ {description}"


# ==================== Physiological Behaviors ====================

@function_tool
def stretch(duration_seconds: int = 5) -> str:
    """Dog stretches body
    
    Args:
        duration_seconds: How long to stretch (default: 5s, range: 3-10s)
    """
    def action():
        state_manager.modify_state(fatigue=-3, happiness=2)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="伸懒腰",
        action_func=action,
        message="伸懒腰，前腿向前伸展...感觉舒服多了！"
    )


@function_tool
def yawn(duration_seconds: int = 3) -> str:
    """Dog yawns
    
    Args:
        duration_seconds: How long to yawn (default: 3s, range: 2-5s)
    """
    def action():
        state_manager.modify_state(fatigue=-2)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="打哈欠",
        action_func=action,
        message="张大嘴巴...哈~~~欠~"
    )


def _queue_long_term_behavior(behavior_type: str, duration: float, description: str, start_message: str, behavior_name: str = None):
    """Add long-term behavior to execution queue"""
    # Get behavior function name for video playback
    if behavior_name is None:
        import inspect
        frame = inspect.currentframe().f_back
        behavior_name = frame.f_code.co_name
    
    if behavior_queue is None:
        # Fallback to immediate execution if no queue
        # Trigger video callback for immediate execution
        if video_callback:
            video_callback(behavior_name)
        success, message = state_manager.start_behavior(behavior_type, duration, description)
        if not success:
            return _log_behavior(message, behavior_display=description)
        return _log_behavior(start_message + message, behavior_display=description)
    
    # Create action to execute later
    def execute_behavior():
        success, message = state_manager.start_behavior(behavior_type, duration, description)
        return message
    
    # Add to queue (video will be triggered when executor starts this task)
    from dog_agent_gradio import BehaviorTask
    task = BehaviorTask(
        behavior_type="long_term",
        action=execute_behavior,
        description=description,
        estimated_duration=duration,
        behavior_name=behavior_name  # Store for later video update
    )
    behavior_queue.put(task)
    
    # Log to console with details
    log_message = f"✓ 计划{description} ({duration:.0f}分钟) - 已加入队列"
    print(f"  🐾 {log_message}")
    
    # Add to behavior history with just the behavior name
    if behavior_callback:
        behavior_callback(description)
    
    # Return simple confirmation to LLM
    return f"✓ {description}"


@function_tool
def drink_water(duration_seconds: int = 480) -> str:
    """Dog drinks water (long-term behavior)
    
    Args:
        duration_seconds: How long to drink in seconds (default: 480s = 8 minutes)
                         Typical range: 300-600s (5-10 minutes)
                         - Very thirsty (>80): 600s (10 min)
                         - Thirsty (>50): 480s (8 min)  
                         - Slightly thirsty: 300s (5 min)
    """
    duration_minutes = duration_seconds / 60
    return _queue_long_term_behavior(
        behavior_type="drinking",
        duration=duration_minutes,
        description="喝水",
        start_message="走向水碗开始喝水... "
    )


@function_tool
def eat_food(duration_seconds: int = 720) -> str:
    """Dog eats food (long-term behavior)
    
    Args:
        duration_seconds: How long to eat in seconds (default: 720s = 12 minutes)
                         Typical range: 300-900s (5-15 minutes)
                         - Very hungry (>80): 900s (15 min)
                         - Hungry (>50): 720s (12 min)
                         - Slightly hungry: 420s (7 min)
    """
    duration_minutes = duration_seconds / 60
    return _queue_long_term_behavior(
        behavior_type="eating",
        duration=duration_minutes,
        description="吃饭",
        start_message="走到食碗前开始吃饭... "
    )


@function_tool
def lick_fur(duration_seconds: int = 30) -> str:
    """Dog licks and grooms fur
    
    Args:
        duration_seconds: How long to groom (default: 30s, range: 10-60s)
    """
    def action():
        state_manager.modify_state(happiness=3, boredom=-2)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="舔毛",
        action_func=action,
        message="舔爪子梳理毛发...保持干净！"
    )


@function_tool
def sleep(duration_seconds: int = 7200) -> str:
    """Dog sleeps (long-term behavior)
    
    Args:
        duration_seconds: How long to sleep in seconds (default: 7200s = 2 hours)
                         Typical range: 1800-14400s (30 min - 4 hours)
                         - Exhausted (>80): 10800-14400s (3-4 hours)
                         - Tired (>50): 7200s (2 hours)
                         - Slightly tired: 1800-3600s (30 min - 1 hour)
                         - Just resting: 900-1800s (15-30 min)
    """
    duration_minutes = duration_seconds / 60
    return _queue_long_term_behavior(
        behavior_type="sleeping",
        duration=duration_minutes,
        description="睡觉",
        start_message="蜷缩起来...闭上眼睛...zzz... "
    )


# ==================== Social Behaviors ====================

@function_tool
def wag_tail(duration_seconds: int = 5) -> str:
    """Dog wags tail happily
    
    Args:
        duration_seconds: How long to wag tail (default: 5s, range: 2-10s)
    """
    def action():
        state_manager.modify_state(happiness=5)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="摇尾巴",
        action_func=action,
        message="尾巴兴奋地摇摆！好开心！"
    )


@function_tool
def nuzzle_owner(duration_seconds: int = 10) -> str:
    """Dog nuzzles against owner
    
    Args:
        duration_seconds: How long to nuzzle (default: 10s, range: 5-20s)
    """
    def action():
        state_manager.modify_state(happiness=8, boredom=-5)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="蹭主人",
        action_func=action,
        message="用头蹭主人的腿...寻求关注！"
    )


@function_tool
def lick_hand(duration_seconds: int = 8) -> str:
    """Dog licks owner's hand
    
    Args:
        duration_seconds: How long to lick (default: 8s, range: 3-15s)
    """
    def action():
        state_manager.modify_state(happiness=7, boredom=-3)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="舔手",
        action_func=action,
        message="深情地舔主人的手...表达爱意！"
    )


@function_tool
def follow_owner(duration_seconds: int = 15) -> str:
    """Dog follows owner around
    
    Args:
        duration_seconds: How long to follow (default: 15s, range: 5-30s)
    """
    def action():
        state_manager.modify_state(happiness=5, boredom=-5)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="跟随主人",
        action_func=action,
        message="紧紧跟随主人...待在主人身边！"
    )


@function_tool
def look_up_at_owner(duration_seconds: int = 3) -> str:
    """Dog looks up at owner
    
    Args:
        duration_seconds: How long to look up (default: 3s, range: 2-10s)
    """
    def action():
        state_manager.modify_state(happiness=3)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="抬头看主人",
        action_func=action,
        message="用大眼睛抬头看着主人...等待关注！"
    )


# ==================== Exploration Behaviors ====================

@function_tool
def sniff_ground(duration_seconds: int = 10) -> str:
    """Dog sniffs the ground
    
    Args:
        duration_seconds: How long to sniff (default: 10s, range: 5-30s)
    """
    def action():
        state_manager.modify_state(boredom=-8, fatigue=2)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="嗅地板",
        action_func=action,
        message="鼻子贴着地面...到处闻闻...调查中！"
    )


@function_tool
def walk_in_circles(duration_seconds: int = 20) -> str:
    """Dog walks in circles
    
    Args:
        duration_seconds: How long to walk in circles (default: 20s, range: 10-60s)
    """
    def action():
        state_manager.modify_state(boredom=-5, fatigue=3)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="绕圈",
        action_func=action,
        message="绕圈走...探索空间！"
    )


@function_tool
def paw_at_object(duration_seconds: int = 15) -> str:
    """Dog paws at objects
    
    Args:
        duration_seconds: How long to paw (default: 15s, range: 5-30s)
    """
    def action():
        state_manager.modify_state(boredom=-10, happiness=5)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="扒东西",
        action_func=action,
        message="用爪子扒有趣的东西...调查中！"
    )


@function_tool
def look_out_window(duration_seconds: int = 60) -> str:
    """Dog looks out the window
    
    Args:
        duration_seconds: How long to look out (default: 60s, range: 30-300s)
    """
    def action():
        state_manager.modify_state(boredom=-12, happiness=5)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="看窗外",
        action_func=action,
        message="看向窗外...观察外面的世界！"
    )


@function_tool
def chase_light(duration_seconds: int = 45) -> str:
    """Dog chases light reflections
    
    Args:
        duration_seconds: How long to chase (default: 45s, range: 20-120s)
    """
    def action():
        state_manager.modify_state(boredom=-15, fatigue=8, happiness=10)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="追光点",
        action_func=action,
        message="追逐光点！兴奋地跑来跑去！"
    )


# ==================== Emotional Expression ====================

@function_tool
def bark(duration_seconds: int = 5) -> str:
    """Dog barks
    
    Args:
        duration_seconds: How long to bark (default: 5s, range: 2-15s)
    """
    def action():
        state_manager.modify_state(boredom=-5)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="吠叫",
        action_func=action,
        message="汪！汪！(吠叫)"
    )


@function_tool
def growl(duration_seconds: int = 8) -> str:
    """Dog growls softly
    
    Args:
        duration_seconds: How long to growl (default: 8s, range: 3-20s)
    """
    def action():
        state_manager.modify_state(happiness=-5)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="低吼",
        action_func=action,
        message="呜呜...(低吼声)"
    )


@function_tool
def pin_ears_back(duration_seconds: int = 5) -> str:
    """Dog pins ears back (nervous/submissive)
    
    Args:
        duration_seconds: How long ears stay back (default: 5s, range: 2-15s)
    """
    def action():
        state_manager.modify_state(happiness=-3)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="耳朵贴后",
        action_func=action,
        message="耳朵贴向脑后...感到不安"
    )


@function_tool
def tuck_tail(duration_seconds: int = 10) -> str:
    """Dog tucks tail between legs (scared/submissive)
    
    Args:
        duration_seconds: How long tail stays tucked (default: 10s, range: 5-30s)
    """
    def action():
        state_manager.modify_state(happiness=-5)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="尾巴夹起",
        action_func=action,
        message="尾巴夹在两腿之间...感到害怕或顺从"
    )


@function_tool
def jump_excitedly(duration_seconds: int = 15) -> str:
    """Dog jumps up and down excitedly
    
    Args:
        duration_seconds: How long to jump (default: 15s, range: 5-30s)
    """
    def action():
        state_manager.modify_state(happiness=8, boredom=-10, fatigue=5)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="蹦跳",
        action_func=action,
        message="上下跳跃！太兴奋了！蹦蹦跳跳！"
    )


# ==================== Training Actions ====================

@function_tool
def sit(duration_seconds: int = 30) -> str:
    """Dog sits down
    
    Args:
        duration_seconds: How long to sit (default: 30s, range: 10-120s)
    """
    def action():
        state_manager.modify_state(happiness=5, fatigue=-3)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="坐下",
        action_func=action,
        message="乖乖坐下...尾巴摇摆！"
    )


@function_tool
def lie_down(duration_seconds: int = 60) -> str:
    """Dog lies down
    
    Args:
        duration_seconds: How long to lie down (default: 60s, range: 30-300s)
    """
    def action():
        state_manager.modify_state(fatigue=-5, happiness=3)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="趴下",
        action_func=action,
        message="平躺在地上...休息！"
    )


@function_tool
def shake_paw(duration_seconds: int = 5) -> str:
    """Dog offers paw to shake
    
    Args:
        duration_seconds: How long to shake paw (default: 5s, range: 3-10s)
    """
    def action():
        state_manager.modify_state(happiness=8, boredom=-5)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="握手",
        action_func=action,
        message="抬起爪子握手...好狗狗的技能！"
    )


@function_tool
def roll_over(duration_seconds: int = 8) -> str:
    """Dog rolls over
    
    Args:
        duration_seconds: How long to roll over (default: 8s, range: 5-15s)
    """
    def action():
        state_manager.modify_state(happiness=10, boredom=-8, fatigue=3)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="打滚",
        action_func=action,
        message="翻滚露出肚皮...展示肚子！棒极了！"
    )


@function_tool
def play_dead(duration_seconds: int = 10) -> str:
    """Dog plays dead
    
    Args:
        duration_seconds: How long to play dead (default: 10s, range: 5-30s)
    """
    def action():
        state_manager.modify_state(happiness=7, boredom=-6)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="装死",
        action_func=action,
        message="夸张地倒下...装死！(舌头伸出)"
    )


@function_tool
def fetch_object(duration_seconds: int = 60) -> str:
    """Dog fetches an object
    
    Args:
        duration_seconds: How long to fetch (default: 60s, range: 30-180s)
    """
    def action():
        state_manager.modify_state(happiness=12, boredom=-15, fatigue=10)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="取物",
        action_func=action,
        message="跑去捡东西...把它叼回来！完美的取物！"
    )


# ==================== Special/Unusual Behaviors ====================

@function_tool
def scratch_itch(duration_seconds: int = 10) -> str:
    """Dog scratches an itch
    
    Args:
        duration_seconds: How long to scratch (default: 10s, range: 5-20s)
    """
    def action():
        state_manager.modify_state(happiness=3)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="抓痒",
        action_func=action,
        message="用后腿抓痒...啊，舒服多了！"
    )


@function_tool
def sneeze(duration_seconds: int = 2) -> str:
    """Dog sneezes
    
    Args:
        duration_seconds: Duration of sneeze (default: 2s, range: 1-3s)
    """
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="打喷嚏",
        action_func=None,
        message="阿嚏！(打喷嚏)"
    )


@function_tool
def shake_body(duration_seconds: int = 5) -> str:
    """Dog shakes whole body
    
    Args:
        duration_seconds: How long to shake (default: 5s, range: 3-8s)
    """
    def action():
        state_manager.modify_state(happiness=3)
    
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="抖毛",
        action_func=action,
        message="用力抖动全身...毛发四处飞扬！"
    )


@function_tool
def snore(duration_seconds: int = 60) -> str:
    """Dog snores while sleeping
    
    Args:
        duration_seconds: How long to snore (default: 60s, range: 30-300s)
    """
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="打呼",
        action_func=None,
        message="呼...呼...(轻轻打呼)"
    )


@function_tool
def dream_twitch(duration_seconds: int = 30) -> str:
    """Dog twitches while dreaming
    
    Args:
        duration_seconds: How long to twitch (default: 30s, range: 10-120s)
    """
    return _queue_behavior(
        behavior_type="instant",
        duration=duration_seconds/60,
        description="梦中抽搐",
        action_func=None,
        message="腿在抽动...爪子在动...(梦见在奔跑！)"
    )


# ==================== Special Control Actions ====================

@function_tool
def interrupt_current_behavior() -> str:
    """Interrupt dog's current long-term behavior (if owner needs dog's attention)"""
    # Note: No video callback here - interrupt doesn't have its own video
    # The next behavior in queue will trigger its video when executed
    
    success, message = state_manager.interrupt_behavior("被主人叫醒/打断")
    behavior_display = "中断当前行为" if success else "无行为可中断"
    return _log_behavior(message, behavior_display=behavior_display)


# ==================== Utility Functions ====================

def get_all_behavior_tools():
    """Get all behavior tools for agent"""
    return [
        # Physiological
        stretch, yawn, drink_water, eat_food, lick_fur, sleep,
        # Social
        wag_tail, nuzzle_owner, lick_hand, follow_owner, look_up_at_owner,
        # Exploration
        sniff_ground, walk_in_circles, paw_at_object, look_out_window, chase_light,
        # Emotional
        bark, growl, pin_ears_back, tuck_tail, jump_excitedly,
        # Training
        sit, lie_down, shake_paw, roll_over, play_dead, fetch_object,
        # Special
        scratch_itch, sneeze, shake_body, snore, dream_twitch,
        # Control
        interrupt_current_behavior
    ]

def get_quick_behaviors():
    """Get list of quick/instant behaviors"""
    return [
        stretch, yawn, lick_fur,
        wag_tail, nuzzle_owner, lick_hand, follow_owner, look_up_at_owner,
        sniff_ground, walk_in_circles, paw_at_object, look_out_window, chase_light,
        bark, growl, pin_ears_back, tuck_tail, jump_excitedly,
        sit, lie_down, shake_paw, roll_over, play_dead, fetch_object,
        scratch_itch, sneeze, shake_body, snore, dream_twitch
    ]

def get_long_term_behaviors():
    """Get list of long-term behaviors"""
    return [drink_water, eat_food, sleep]

