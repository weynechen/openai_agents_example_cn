"""
Dog state management with SQLite persistence.
Manages internal states: hunger, thirst, fatigue, boredom, happiness
"""

import sqlite3
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class DogState:
    """Dog's internal state"""
    hunger: float = 20.0      # 0-100, increases over time
    thirst: float = 20.0      # 0-100, increases over time
    fatigue: float = 20.0     # 0-100, increases over time
    boredom: float = 30.0     # 0-100, increases over time
    happiness: float = 70.0   # 0-100, affected by interactions
    last_update_time: float = None
    
    # Long-term behavior tracking
    current_behavior: str = None           # e.g., "sleeping", "eating"
    behavior_start_time: float = None      # When behavior started
    behavior_duration: float = None        # Expected duration in minutes
    behavior_description: str = None       # Display description
    
    def __post_init__(self):
        if self.last_update_time is None:
            self.last_update_time = time.time()
    
    def to_dict(self):
        """Convert to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict):
        """Create from dictionary"""
        return cls(**data)
    
    def clamp_values(self):
        """Ensure all values are within 0-100 range"""
        self.hunger = max(0, min(100, self.hunger))
        self.thirst = max(0, min(100, self.thirst))
        self.fatigue = max(0, min(100, self.fatigue))
        self.boredom = max(0, min(100, self.boredom))
        self.happiness = max(0, min(100, self.happiness))
    
    def get_status_text(self) -> str:
        """Get readable status text"""
        return f"""
🐕 狗狗状态:
  饥饿值: {self.hunger:.1f}/100 {'⚠️  (饿了!)' if self.hunger > 70 else ''}
  口渴值: {self.thirst:.1f}/100 {'⚠️  (渴了!)' if self.thirst > 70 else ''}
  疲劳值: {self.fatigue:.1f}/100 {'⚠️  (累了!)' if self.fatigue > 70 else ''}
  无聊值: {self.boredom:.1f}/100 {'⚠️  (无聊!)' if self.boredom > 70 else ''}
  快乐值: {self.happiness:.1f}/100 {'😊' if self.happiness > 70 else '😐' if self.happiness > 30 else '😞'}
"""


class DogStateManager:
    """Manage dog state with SQLite persistence"""
    
    def __init__(self, db_path: str = "dog_state.db", time_scale: float = 1.0):
        self.db_path = db_path
        # Allow connection to be used across threads
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()
        self.current_state = self._load_or_create_state()
        
        # Time scale: 1.0 = real-time, 60.0 = 1 second = 1 minute
        self.time_scale = time_scale
    
    def _init_db(self):
        """Initialize database schema"""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dog_state (
                id INTEGER PRIMARY KEY,
                state_data TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        self.conn.commit()
    
    def _load_or_create_state(self) -> DogState:
        """Load existing state or create new one"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT state_data FROM dog_state WHERE id = 1")
        row = cursor.fetchone()
        
        if row:
            state_dict = json.loads(row[0])
            return DogState.from_dict(state_dict)
        else:
            # Create initial state
            return DogState()
    
    def update_state_by_time(self):
        """Update state based on elapsed time"""
        current_time = time.time()
        elapsed_seconds = current_time - self.current_state.last_update_time
        # Apply time scale
        elapsed_minutes = (elapsed_seconds * self.time_scale) / 60.0
        
        # Update long-term behavior if active
        if self.current_state.current_behavior:
            self._update_behavior_progress(elapsed_minutes)
        
        # Update values based on time (only if not sleeping)
        if self.current_state.current_behavior != "sleeping":
            self.current_state.hunger += elapsed_minutes * 2.0    # +2 per minute
            self.current_state.thirst += elapsed_minutes * 1.5    # +1.5 per minute
            self.current_state.fatigue += elapsed_minutes * 1.0   # +1 per minute
            self.current_state.boredom += elapsed_minutes * 1.5   # +1.5 per minute
        
        # Unhappiness increases if needs are not met
        if self.current_state.hunger > 70 or self.current_state.thirst > 70:
            self.current_state.happiness -= elapsed_minutes * 0.5
        
        self.current_state.last_update_time = current_time
        self.current_state.clamp_values()
    
    def _update_behavior_progress(self, elapsed_minutes: float):
        """Update progress of current long-term behavior"""
        if not self.current_state.current_behavior:
            return
        
        behavior = self.current_state.current_behavior
        current_time = time.time()
        behavior_elapsed_seconds = current_time - self.current_state.behavior_start_time
        behavior_elapsed_minutes = (behavior_elapsed_seconds * self.time_scale) / 60.0
        
        # Check if behavior is complete
        if behavior_elapsed_minutes >= self.current_state.behavior_duration:
            self._complete_behavior()
            return
        
        # Apply continuous effects based on behavior type
        progress = behavior_elapsed_minutes / self.current_state.behavior_duration
        
        if behavior == "sleeping":
            # Continuous fatigue reduction while sleeping
            self.current_state.fatigue = max(0, 80 * (1 - progress))
            self.current_state.boredom = max(0, 50 * (1 - progress * 0.5))
            
        elif behavior == "eating":
            # Continuous hunger reduction while eating
            initial_hunger = getattr(self.current_state, '_eating_initial_hunger', 80)
            self.current_state.hunger = max(0, initial_hunger * (1 - progress))
            
        elif behavior == "drinking":
            # Continuous thirst reduction while drinking
            initial_thirst = getattr(self.current_state, '_drinking_initial_thirst', 80)
            self.current_state.thirst = max(0, initial_thirst * (1 - progress))
    
    def _complete_behavior(self):
        """Complete current behavior and apply final effects"""
        behavior = self.current_state.current_behavior
        
        if behavior == "sleeping":
            self.current_state.fatigue = 0
            self.current_state.happiness += 10
            print(f"[BEHAVIOR] ✅ Dog finished sleeping, fully rested!")
            
        elif behavior == "eating":
            self.current_state.hunger = 0
            self.current_state.happiness += 15
            print(f"[BEHAVIOR] ✅ Dog finished eating, fully fed!")
            
        elif behavior == "drinking":
            self.current_state.thirst = 0
            self.current_state.happiness += 10
            print(f"[BEHAVIOR] ✅ Dog finished drinking, fully hydrated!")
        
        # Clear behavior
        self.current_state.current_behavior = None
        self.current_state.behavior_start_time = None
        self.current_state.behavior_duration = None
        self.current_state.behavior_description = None
        
        # Set flag to indicate behavior just completed
        self.current_state._behavior_just_completed = True
        
        self.save_state()
    
    def check_and_clear_completion_flag(self) -> bool:
        """Check if a behavior just completed and clear the flag"""
        if hasattr(self.current_state, '_behavior_just_completed') and self.current_state._behavior_just_completed:
            self.current_state._behavior_just_completed = False
            return True
        return False
    
    def start_behavior(self, behavior_type: str, duration_minutes: float, description: str):
        """Start a long-term behavior"""
        if self.is_busy():
            return False, f"狗狗正在{self.current_state.behavior_description}，不能开始新行为"
        
        self.current_state.current_behavior = behavior_type
        self.current_state.behavior_start_time = time.time()
        self.current_state.behavior_duration = duration_minutes
        self.current_state.behavior_description = description
        
        # Store initial values for some behaviors
        if behavior_type == "eating":
            self.current_state._eating_initial_hunger = self.current_state.hunger
        elif behavior_type == "drinking":
            self.current_state._drinking_initial_thirst = self.current_state.thirst
        
        self.save_state()
        
        actual_duration = duration_minutes / self.time_scale
        print(f"[BEHAVIOR] Started {behavior_type} for {duration_minutes} virtual minutes (actual: {actual_duration:.1f} minutes)")
        
        return True, f"开始{description}... (需要 {duration_minutes:.0f} 分钟)"
    
    def interrupt_behavior(self, reason: str = "被主人打断"):
        """Interrupt current behavior"""
        if not self.current_state.current_behavior:
            return False, "狗狗没有在做需要打断的事情"
        
        behavior = self.current_state.current_behavior
        print(f"[BEHAVIOR] {behavior} interrupted: {reason}")
        
        # Clear behavior without completing
        self.current_state.current_behavior = None
        self.current_state.behavior_start_time = None
        self.current_state.behavior_duration = None
        self.current_state.behavior_description = None
        
        self.save_state()
        return True, f"{reason}，停止了之前的行为"
    
    def is_busy(self) -> bool:
        """Check if dog is currently doing a long-term behavior"""
        if not self.current_state.current_behavior:
            return False
        
        current_time = time.time()
        elapsed_seconds = current_time - self.current_state.behavior_start_time
        elapsed_minutes = (elapsed_seconds * self.time_scale) / 60.0
        
        return elapsed_minutes < self.current_state.behavior_duration
    
    def get_behavior_progress(self) -> dict:
        """Get progress information of current behavior"""
        if not self.current_state.current_behavior:
            return None
        
        current_time = time.time()
        elapsed_seconds = current_time - self.current_state.behavior_start_time
        elapsed_minutes = (elapsed_seconds * self.time_scale) / 60.0
        
        remaining_minutes = max(0, self.current_state.behavior_duration - elapsed_minutes)
        progress_percent = min(100, (elapsed_minutes / self.current_state.behavior_duration) * 100)
        
        return {
            "behavior": self.current_state.current_behavior,
            "description": self.current_state.behavior_description,
            "elapsed_minutes": elapsed_minutes,
            "remaining_minutes": remaining_minutes,
            "total_minutes": self.current_state.behavior_duration,
            "progress_percent": progress_percent
        }
    
    def save_state(self):
        """Save current state to database"""
        cursor = self.conn.cursor()
        state_json = json.dumps(self.current_state.to_dict())
        
        cursor.execute("""
            INSERT OR REPLACE INTO dog_state (id, state_data, updated_at)
            VALUES (1, ?, ?)
        """, (state_json, time.time()))
        
        self.conn.commit()
    
    def modify_state(self, **kwargs):
        """Modify state values (delta changes)"""
        for key, value in kwargs.items():
            if hasattr(self.current_state, key):
                current = getattr(self.current_state, key)
                setattr(self.current_state, key, current + value)
        
        self.current_state.clamp_values()
        self.save_state()
    
    def get_state_description(self) -> str:
        """Get state description for agent context"""
        self.update_state_by_time()
        self.save_state()
        
        state = self.current_state
        
        # Check if busy with long-term behavior
        if self.is_busy():
            progress = self.get_behavior_progress()
            return f"""当前状态: 正在{progress['description']}
- 已进行: {progress['elapsed_minutes']:.1f} 分钟
- 还需要: {progress['remaining_minutes']:.1f} 分钟
- 进度: {progress['progress_percent']:.1f}%

注意: 狗狗正忙着，无法执行其他长时间行为。可以执行快速行为如摇尾巴、吠叫等，或者主人可以打断当前行为。"""
        
        # Determine needs
        needs = []
        if state.hunger > 70:
            needs.append("非常饿")
        elif state.hunger > 40:
            needs.append("有点饿")
        
        if state.thirst > 70:
            needs.append("非常渴")
        elif state.thirst > 40:
            needs.append("有点渴")
        
        if state.fatigue > 80:
            needs.append("筋疲力尽")
        elif state.fatigue > 50:
            needs.append("累了")
        
        if state.boredom > 70:
            needs.append("非常无聊")
        elif state.boredom > 40:
            needs.append("有点无聊")
        
        needs_text = "、".join(needs) if needs else "满足"
        
        return f"""当前内部状态:
- 饥饿值: {state.hunger:.1f}/100
- 口渴值: {state.thirst:.1f}/100
- 疲劳值: {state.fatigue:.1f}/100
- 无聊值: {state.boredom:.1f}/100
- 快乐值: {state.happiness:.1f}/100
- 整体感觉: {needs_text}"""
    
    def close(self):
        """Close database connection"""
        self.conn.close()

