# Agenthle

This is the onboarding repository for Agenthle engineers. It contains the most basic code and submodules for the project, which is [Cua](https://cua.ai/docs/cua/guide/get-started/what-is-cua). 

## Structure

```
agenthle/
├── submodules/
│   └── cua/ # cua submodule
└── tasks/
    └── magic_tower_easy/ # demo task
        ├── main.py # task entry, where the task config, setup, and verification are defined
        ├── run_magic_tower_easy.sh # bash script to run the demo task by running the Cua framework
    └── your_task/ # your task directory, put all the files related to your task in this directory and zip it to deliver

```

## Setup

### 1. Clone the repository

```bash
git clone --recursive git@github.com:cua-verse/agenthle-base.git
cd agenthle-base
```

### 2. Install uv

If you don't have uv installed:

```bash
# on mac
brew install uv
```

Or follow the [official installation guide](https://github.com/astral-sh/uv#installation).

Install all dependencies:

```bash
uv sync
```

This will:
- Create a virtual environment in `.venv`
- Install all dependencies from both `agenthle` and `cua` packages
- Install all packages in editable mode
