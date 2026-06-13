# LeetCode-Lab

Automated data pipeline for evaluating LLM-generated code on LeetCode.

[Deutsche Version](README.de.md)

## Description

This project imports selected LeetCode problems through the LeetCode GraphQL
interface. It then uses the OpenAI API to generate solutions in the configured
programming languages and submit them to LeetCode. The official submission
results are stored so the selected model can be evaluated in a structured,
dataset-based workflow.

It was originally developed as my bachelor project for the winter semester
2025/26 and was uploaded later in a cleaned-up public form.

## Features

- Select and import LeetCode problems from a configuration file.
- Generate a standardized prompt from each imported problem.
- Generate solutions in the configured programming languages through the OpenAI API.
- Submit generated solutions to LeetCode automatically.
- Record LeetCode status, runtime, memory, passed tests, model, and submission
  ID in a spreadsheet-friendly CSV file.

## Requirements

- Python 3.9 or newer
- stable internet connection
- logged-in LeetCode browser session
- OpenAI API key

## Setup

### Step 1: Clone The Repository

```bash
git clone https://github.com/volkantez/LeetCode-Lab.git
cd LeetCode-Lab
```

### Step 2: Configure Environment Variables

Copy `.env.example` and create a local `.env` file in the project directory:

```bash
cp .env.example .env
```

Then add the required values:

```env
OPENAI_API_KEY=your_openai_api_key
CSRF_TOKEN=your_csrftoken_cookie
LEETCODE_SESSION=your_LEETCODE_SESSION_cookie
```

`OPENAI_API_KEY` is required for automatic solution generation. You can create
an API key on the [OpenAI API keys page](https://platform.openai.com/api-keys).

`LEETCODE_SESSION` and `CSRF_TOKEN` are required for official LeetCode
submissions. You can find them in your browser after logging
in to LeetCode:

1. Open `https://leetcode.com` in your browser.
2. Open the developer tools.
3. Open the `Application` or `Storage` tab.
4. Select `https://leetcode.com` under `Cookies`.
5. Copy the values of the `LEETCODE_SESSION` and `csrftoken` cookies into your
   `.env` file.

### Step 3: Import Dataset

Problems are selected and imported based on `LeetCodeConfig.json`. The dataset
name, programming languages, and model are configured there as well. The default
model is `gpt-5.2`.

In practice, separate datasets should be used for different models, prompts, or
experiment configurations.

```bash
# macOS / Linux
python3 -m src.cli import.dataset

# Windows
py -3 -m src.cli import.dataset
```

The dataset name is configured through `dataset`. Languages are configured
through `languages`. Example:

```json
"dataset": "leetcode_2514_2550_gpt5.2",
"languages": ["python3", "cpp"]
```

Each language gets its own imported problem JSON files:

```text
datasets/<dataset>/problems/<language>/
```

Common language values are `python`, `python3`, `cpp`, `java`, `javascript`,
`typescript`, `csharp`, `golang`, `rust`, `kotlin`, `swift`, and `php`.

### Step 4: Solve And Submit Dataset

All imported problems from the configured `dataset` are solved and submitted
for each language listed in `languages`:

```bash
# macOS / Linux
python3 -m src.cli submit.dataset

# Windows
py -3 -m src.cli submit.dataset
```

Generated solutions are stored per dataset and language:

```text
datasets/<dataset>/solutions/<language>/
```

Detailed LeetCode responses and compact results are stored here:

```text
datasets/<dataset>/results
```

Problems that were already solved successfully are skipped automatically on the
next run within the same dataset and language.

## Adjust Prompt

The input for the OpenAI model is generated from this template:

```text
default_prompt.txt
```

This template can be adjusted to influence the behavior of the generated
solutions.

## Scope And Limitations

Correctness is evaluated through official LeetCode submissions. This means that
LeetCode's hidden test cases are included in the evaluation.

Submission uses private LeetCode session cookies and direct HTTP requests to
LeetCode endpoints. It can fail if the session expires, LeetCode changes its
endpoints, Cloudflare blocks the request, or LeetCode rate-limits submissions.
If the cookies expire, the values in `.env` must be updated with fresh
`LEETCODE_SESSION` and `CSRF_TOKEN` values from the browser.

## License

[LICENSE](LICENSE)
