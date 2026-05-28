ROUTER_PROMPT = """\
Classify the user's message into exactly one intent.

- **chat**: Greetings, general questions, small talk, help requests.
- **control**: Perform a single action on ONE device (turn on/off, set value, trigger).
	Also use control for automation job management requests (create/list/check/delete jobs).
- **analysis**: Explore, visualise, or understand data from devices. \
Also covers piping or transforming data between devices.

If the user asks about existing jobs (for example "list jobs", "which jobs are active", "job status"), classify as **control**.
If the user asks to debug jobs/automations or interpret a job "last result", classify as **control**.
"""
