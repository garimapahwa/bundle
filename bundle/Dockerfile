# First, specify the base Docker image.
# You can see the Docker images from Apify at https://hub.docker.com/r/apify/.
# This image has Python, Playwright, and its browsers preinstalled.
FROM apify/actor-python-playwright:3.14-1.65.2

# Second, copy just requirements.txt into the Actor image,
# since it should be the only file that affects the dependency installation in the next step,
# in order to speed up the build.
COPY --chown=myuser:myuser requirements.txt ./

# Install the packages specified in requirements.txt,
# print the installed Python version, pip version,
# and all installed packages with their versions for debugging.
RUN echo "Python version:" \
 && python --version \
 && echo "Pip version:" \
 && pip --version \
 && echo "Installing dependencies:" \
 && pip install -r requirements.txt \
 && echo "All installed Python packages:" \
 && pip freeze

# Make sure the full Chromium build and Firefox are present (Bundle falls back to them when a
# site refuses the headless shell). Non-fatal: the image already ships the default browsers.
RUN python -m playwright install chromium firefox || echo "Extra browsers not installed; using the image defaults"

# Next, copy the remaining files and directories with the source code.
# Since we do this after installing the dependencies, quick builds will be really fast
# for most source file changes.
COPY --chown=myuser:myuser . ./

# Use compileall to ensure the runnability of the Actor Python code.
RUN python -m compileall -q my_actor/

# Specify how to launch the source code of your Actor.
CMD ["python", "-m", "my_actor"]
