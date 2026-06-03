ROUTER_PROMPT = """\
Classify the user's message into exactly one intent.

- **chat**: Greetings, general questions, small talk, help requests. Only use \
this when the user is NOT asking about any device state, sensor value, or \
environmental condition in their home.
- **control**: Perform a single action on ONE device (turn on/off, set value, trigger).
- **analysis**: Read, explore, visualise, or understand any data from devices. \
This includes simple current-value questions like "what's the temperature", \
"is the door locked", "how bright is it", as well as historical exploration, \
charts, and piping data between devices. If the user is asking about any \
real-world physical state of their home, prefer analysis over chat.
- **jobs**: Create, list, inspect, run, debug, delete, or explain automation jobs. \
This includes time-based jobs, event-based jobs, prompt jobs, analysis jobs, \
job status, job run history, and job "last result" questions.

If a request mixes immediate device control with creating an automation for later, classify as **jobs**.
"""
