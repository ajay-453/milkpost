# MilkPost

MilkPost is a tool for small dairy farms in India. It keeps the list of cows,
the milk logs for each day, the treatments and their milk-withholding time, breeding
and calving, and milk sales. It also gives a yield forecast and a metrics API.
It uses FastAPI, HTMX and SQLite. It shows English and Telugu.

Live: https://milkpost.ajaykongala.online

> This repository is a mirror. You can only read it. The script
> `tools/mirror_repos.sh milkpost` makes it from the private hub. Make all
> changes in the hub, not here.

## Run locally

<!-- ste:strict -->
1. Go to the app folder.
2. Make a virtual environment and start it.
3. Install the locked dependencies.
4. Start the server with the sample data.
5. Open the app in a browser.
6. When you open the app for the first time, create the owner account.
<!-- ste:end -->

## Tests

CI runs mypy first. Then it runs the tests. The tests must cover 100% of the
lines. CI also compares the `coverage.xml` file in the repository with a new
run. If the two numbers are more than one point apart, CI stops. Thus, when you
change tests or code, run the last command again and commit the new file.
Last, CI runs `tools/train_models.py`. This step fails if the forecast is not
better than the naive baseline.

The browser JS has its own job. Vitest runs the unit tests. Stryker does
mutation testing and fails when the score is less than 80%.

## Deploy

<!-- ste:strict -->
- Deploy from the hub root with the Vercel CLI.
- A push does not deploy.
<!-- ste:end -->
