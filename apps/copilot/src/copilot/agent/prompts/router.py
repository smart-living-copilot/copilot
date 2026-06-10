ROUTER_PROMPT = """\
Classify the user's message into exactly one intent.

- **chat**: Greetings, general questions, small talk, help requests. Only use \
this when the user is NOT asking about any device state, sensor value, or \
environmental condition in their home, and is NOT asking to build any kind of \
interface. Building a UI is never chat.
- **control**: Perform an action on a device (turn on/off, set value, trigger), \
OR build an interactive control panel, UI, widget, or interface to operate one \
or more devices (e.g. "build a control panel for the lamp", "give me buttons to \
toggle the lights", "make a widget to control the thermostat").
- **analysis**: Read, explore, visualise, or understand any data from devices, \
registered SPARQL endpoints, or external knowledge graphs. \
This includes simple current-value questions like "what's the temperature", \
"is the door locked", "how bright is it", as well as historical exploration, \
charts, piping data between devices, and building a live dashboard or monitoring \
interface to view device data. If the user asks to find or use a SPARQL endpoint \
Thing, RDF graph, knowledge graph, or RDF entity, classify as analysis. \
If the user is asking about any real-world \
physical state of their home, prefer analysis over chat.
- **jobs**: Create, list, inspect, run, debug, delete, or explain automation jobs. \
This includes time-based jobs, event-based jobs, prompt jobs, analysis jobs, \
job status, job run history, and job "last result" questions.

If a request mixes immediate device control with creating an automation for later, classify as **jobs**.
Any request to build, create, or make a UI, panel, dashboard, widget, or \
interface for the home is **control** (to operate devices) or **analysis** (to \
view data) — never chat.
"""
