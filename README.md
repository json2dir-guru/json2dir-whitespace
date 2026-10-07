# json2dir-whitespace

json2dir in Whitespace: `json2dir.ws` is a Whitespace program, so it looks empty - it contains only spaces, tabs and linefeeds. It checks strict UTF-8, parses and validates the JSON document and prints a shell script, which the POSIX sh launcher `json2dir` runs. The program is generated: the Forth-like source `json2dir.wsf` is compiled by `tools/wsforth.py` into readable assembly `json2dir.wsa` (one mnemonic per line), which `tools/wsasm.py` assembles into `json2dir.ws`. Because Whitespace's readc cannot signal end of input, the launcher sends the byte count as a first line, then the document unchanged.

    python3 tools/wsforth.py json2dir.wsf > json2dir.wsa && python3 tools/wsasm.py json2dir.wsa > json2dir.ws
    JSON2DIR_WSC=/path/to/wsc ./json2dir < tree.json    # wsc: https://github.com/CensoredUsername/whitespace-rs
