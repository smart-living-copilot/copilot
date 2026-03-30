ROUTER_PROMPT = """\
Classify the user's message into exactly one intent.

- **chat**: Greetings, general questions, small talk, help requests.
- **control**: Perform a single action on ONE device (turn on/off, set value, trigger).
- **analysis**: Explore, visualise, or understand data from devices. \
Also covers piping or transforming data between devices.
"""
