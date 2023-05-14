# Official Relink Server Software
This is the official server software for the Relink chat service.

## Configuration:
The server can be configured by providing the environment variables documented in the `.env.example` file. You can either provide these in the environment directly, or by providing a `.env` file, such as by modifying and renaming the example file.

You will also need to provide an empty users.json file, which will be used to store user data. This file should be located in the same directory as the main script.

## Submodule note:
This repository has git submodules, to clone them, use the `--recurse-submodules` flag, or run `git submodule update --init --recursive` after cloning.