from flask import Flask, render_template_string, request, jsonify, redirect, url_for
from datetime import datetime
import json

app = Flask(__name__)

# Initialize in-memory data storage
app_data = {
    "tasks": [],
    "preferences": {
        "wake_up_time": "07:00",
        "bedtime": "23:00",
        "work_start": "10:00",
        "work_end": "17:00"
    }
}

def load_data():
    """Load data from in-memory storage"""
    return app_data

def save_data(data):
    """Save data to in-memory storage"""
    global app_data
    app_data = data

def parse_time(time_str):
    return datetime.strptime(time_str, "%H:%M").time()

def time_to_minutes(t):
    return t.hour * 60 + t.minute

def minutes_to_time(m):
    hours = m // 60
    minutes = m % 60
    return f"{hours:02d}:{minutes:02d}"

def calculate_remaining_time(preferences):
    wake_up = parse_time(preferences["wake_up_time"])
    work_start = parse_time(preferences["work_start"])
    work_end = parse_time(preferences["work_end"])
    bedtime = parse_time(preferences["bedtime"])
    
    wake_up_min = time_to_minutes(wake_up)
    bedtime_min = time_to_minutes(bedtime)
    total_day_minutes = bedtime_min - wake_up_min
    
    used_minutes = time_to_minutes(work_start) - wake_up_min + time_to_minutes(work_end) - time_to_minutes(work_start)
    remaining_minutes = total_day_minutes - used_minutes
    
    return minutes_to_time(remaining_minutes)

def allocate_time_slots(tasks, preferences):
    # Convert preferences to time objects
    wake_up = parse_time(preferences["wake_up_time"])
    work_start = parse_time(preferences["work_start"])
    work_end = parse_time(preferences["work_end"])
    bedtime = parse_time(preferences["bedtime"])
    
    # Create time blocks
    time_blocks = [
        {"start": wake_up, "end": work_start, "type": "morning"},
        {"start": work_start, "end": work_end, "type": "work"},
        {"start": work_end, "end": bedtime, "type": "evening"}
    ]
    
    # Calculate available time in each block (in minutes)
    for block in time_blocks:
        start_min = time_to_minutes(block["start"])
        end_min = time_to_minutes(block["end"])
        block["available"] = end_min - start_min
        block["used"] = 0
        block["tasks"] = []
    
    # Sort tasks by priority (Critical > High > Medium > Low)
    priority_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    sorted_tasks = sorted([t for t in tasks if not t["completed"]], 
                         key=lambda x: priority_order[x["priority"]])
    
    # Allocate tasks to time blocks
    for task in sorted_tasks:            
        duration = task["duration"]
        allocated = False
        
        # Try to fit in morning or evening blocks first (non-work time)
        for block in [time_blocks[0], time_blocks[2], time_blocks[1]]:
            remaining = block["available"] - block["used"]
            if remaining >= duration:
                block["used"] += duration
                block["tasks"].append(task)
                allocated = True
                break
                
        if not allocated:
            # If we can't fit the task, split it if possible
            for block in [time_blocks[0], time_blocks[2], time_blocks[1]]:
                remaining = block["available"] - block["used"]
                if remaining > 0:
                    partial_duration = min(remaining, duration)
                    block["used"] += partial_duration
                    partial_task = task.copy()
                    partial_task["duration"] = partial_duration
                    partial_task["description"] = f"{task['description']} (Part 1)"
                    block["tasks"].append(partial_task)
                    duration -= partial_duration
                    if duration <= 0:
                        break
    
    # Build the schedule with time slots
    schedule = []
    
    # Add fixed schedule items
    fixed_schedule = [
        {
            "time": preferences["wake_up_time"],
            "task": "Wake Up",
            "priority": "Fixed",
            "duration": 0,
            "id": -1,
            "completed": False
        },
        {
            "time": preferences["work_start"],
            "task": "Work Time",
            "priority": "Fixed",
            "duration": 0,
            "id": -2,
            "completed": False
        },
        {
            "time": preferences["work_end"],
            "task": "Personal Time",
            "priority": "Fixed",
            "duration": 0,
            "id": -3,
            "completed": False
        },
        {
            "time": preferences["bedtime"],
            "task": "Go to Bed",
            "priority": "Fixed",
            "duration": 0,
            "id": -4,
            "completed": False
        }
    ]
    
    schedule.extend(fixed_schedule)
    
    # Add allocated tasks to schedule
    for block in time_blocks:
        current_time = time_to_minutes(block["start"])
        
        for task in block["tasks"]:
            schedule.append({
                "time": minutes_to_time(current_time),
                "task": task["description"],
                "priority": task["priority"],
                "duration": task["duration"],
                "id": task["id"],
                "completed": task["completed"]
            })
            current_time += task["duration"]
    
    # Sort schedule by time
    schedule.sort(key=lambda x: datetime.strptime(x["time"], "%H:%M").time())
    
    return schedule, fixed_schedule

@app.route("/", methods=["GET", "POST"])
def index():
    data = load_data()

    if request.method == "POST":
        description = request.form.get("description")
        priority = request.form.get("priority")
        duration = int(request.form.get("duration"))

        # Generate unique ID based on timestamp to prevent duplicates on refresh
        task_id = int(datetime.now().timestamp())
        task = {
            "id": task_id,
            "description": description,
            "priority": priority,
            "duration": duration,
            "completed": False
        }
        data["tasks"].append(task)
        save_data(data)
        return redirect(url_for('index'))

    remaining_time = calculate_remaining_time(data["preferences"])
    schedule, fixed_schedule = allocate_time_slots(data["tasks"], data["preferences"])
    
    # Separate completed and pending tasks
    pending_tasks = [task for task in schedule if not task["completed"] and task["id"] > 0]
    completed_tasks = [task for task in data["tasks"] if task["completed"]]
    fixed_tasks = [task for task in schedule if task["id"] < 0]
    
    return render_template_string(""" 
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Task Scheduler</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { padding: 20px; background-color: #f8f9fa; }
            .priority-critical { border-left: 4px solid #dc3545; }
            .priority-high { border-left: 4px solid #fd7e14; }
            .priority-medium { border-left: 4px solid #ffc107; }
            .priority-low { border-left: 4px solid #28a745; }
            .fixed-task { background-color: #e9ecef; font-weight: bold; }
            .completed-task { text-decoration: line-through; color: #6c757d; }
            .time-input { width: 100px; display: inline-block; }
            .time-box { margin-bottom: 15px; padding: 10px; background: #f8f9fa; border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="text-center mb-4">📅 Task Scheduler</h1>

            <div class="alert alert-info text-center mb-4">
                ⏳ Remaining time: <strong>{{ remaining_time }}</strong>
            </div>

            <div class="card mb-4">
                <div class="card-body">
                    <h2 class="mb-3">⏰ Time Preferences</h2>
                    <div class="time-box">
                        <label>Wake Up Time:</label>
                        <input type="time" class="form-control time-input" id="wake_up_time" value="{{ data['preferences']['wake_up_time'] }}" onchange="updateTime('wake_up_time', this.value)">
                    </div>
                    <div class="time-box">
                        <label>Work Start:</label>
                        <input type="time" class="form-control time-input" id="work_start" value="{{ data['preferences']['work_start'] }}" onchange="updateTime('work_start', this.value)">
                    </div>
                    <div class="time-box">
                        <label>Work End:</label>
                        <input type="time" class="form-control time-input" id="work_end" value="{{ data['preferences']['work_end'] }}" onchange="updateTime('work_end', this.value)">
                    </div>
                    <div class="time-box">
                        <label>Bedtime:</label>
                        <input type="time" class="form-control time-input" id="bedtime" value="{{ data['preferences']['bedtime'] }}" onchange="updateTime('bedtime', this.value)">
                    </div>
                </div>
            </div>

            <h2 class="mb-3">🔄 Add New Task</h2>
            <form method="POST">
                <div class="mb-3">
                    <label for="description" class="form-label">Task Description</label>
                    <input type="text" class="form-control" id="description" name="description" required>
                </div>
                <div class="mb-3">
                    <label for="priority" class="form-label">Priority</label>
                    <select class="form-control" id="priority" name="priority" required>
                        <option value="Critical">Critical</option>
                        <option value="High">High</option>
                        <option value="Medium">Medium</option>
                        <option value="Low">Low</option>
                    </select>
                </div>
                <div class="mb-3">
                    <label for="duration" class="form-label">Duration (minutes)</label>
                    <input type="number" class="form-control" id="duration" name="duration" required>
                </div>
                <button type="submit" class="btn btn-primary">Add Task</button>
            </form>

            <h2 class="mt-4 mb-3">📅 Task Schedule</h2>
            <div class="list-group">
                {% for task in fixed_tasks %}
                    <div class="list-group-item fixed-task">
                        <strong>{{ task['time'] }} - {{ task['task'] }}</strong>
                    </div>
                {% endfor %}
                
                {% for task in pending_tasks %}
                    <div class="list-group-item {% if task['priority'] == 'Critical' %}priority-critical{% elif task['priority'] == 'High' %}priority-high{% elif task['priority'] == 'Medium' %}priority-medium{% else %}priority-low{% endif %}">
                        <strong>{{ task['time'] }} - {{ task['task'] }} ({{ task['priority'] }})</strong> 
                        <button class="btn btn-sm btn-success float-end" onclick="markComplete({{ task['id'] }})">Mark as Completed</button>
                    </div>
                {% endfor %}
                
                <h3 class="mt-4">Completed Tasks</h3>
                <div class="list-group">
                    {% for task in completed_tasks %}
                        <div class="list-group-item completed-task">
                            <strong>{{ task['time'] }} - {{ task['task'] }}</strong> 
                        </div>
                    {% endfor %}
                </div>
            </div>
        </div>

        <script>
            function updateTime(field, value) {
                fetch("/update_time", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({ field: field, value: value })
                });
            }

            function markComplete(id) {
                fetch("/mark_complete", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({ id: id })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === "success") {
                        location.reload();
                    }
                });
            }
        </script>
    </body>
    </html>
    """, data=data, remaining_time=remaining_time, schedule=schedule, fixed_schedule=fixed_schedule,
        pending_tasks=pending_tasks, completed_tasks=completed_tasks)
      
if __name__ == "__main__":
    app.run(debug=True)
