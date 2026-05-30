ROUTER_PROMPT = """\
Classify the user's message into exactly one intent.

- **chat**: Greetings, general questions, small talk, help requests. Only use \
this when the user is NOT asking about any device state, sensor value, or \
environmental condition in their home.
- **control**: Perform a single action on ONE device (turn on/off, set value, trigger).
	Also use control for automation job management requests (create/list/check/delete jobs).
- **analysis**: Read, explore, visualise, or understand any data from devices. \
This includes simple current-value questions like "what's the temperature", \
"is the door locked", "how bright is it", as well as historical exploration, \
charts, and piping data between devices. If the user is asking about any \
real-world physical state of their home, prefer analysis over chat.

If the user asks about existing jobs (for example "list jobs", "which jobs are active", "job status"), classify as **control**.
If the user asks to debug jobs/automations or interpret a job "last result", classify as **control**.
"""
