FROM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git xz-utils unzip file procps xvfb xauth ffmpeg libgl1 libglib2.0-0 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://nodejs.org/dist/v22.11.0/node-v22.11.0-linux-x64.tar.xz | tar xJ -C /usr/local --strip-components=1
RUN pip install --no-cache-dir pydantic==2.10.3 pytest==8.3.4 pyyaml==6.0.2 requests==2.32.3 pypdf==5.1.0
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DISPLAY=:99 MPLBACKEND=Agg
RUN mkdir -p /workspace/inputs /workspace/outputs /skill
RUN apt-get update && apt-get install -y --no-install-recommends unzip libgl1 libgl1-mesa-dri libegl1 libgles2 libxcursor1 libxinerama1 libxrandr2 libxi6 libxkbcommon0 libxrender1 libasound2 libpulse0 libfontconfig1 fonts-dejavu-core xvfb xauth libglx-mesa0 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pillow==11.0.0
RUN curl -fsSL -o /tmp/godot.zip https://github.com/godotengine/godot/releases/download/4.4.1-stable/Godot_v4.4.1-stable_linux.x86_64.zip && unzip -q /tmp/godot.zip -d /opt/godot && mv /opt/godot/Godot_v4.4.1-stable_linux.x86_64 /usr/local/bin/godot && chmod 755 /usr/local/bin/godot && rm -rf /tmp/godot.zip /opt/godot
RUN mkdir -p /opt/godot-data/godot/export_templates/4.4.1.stable && curl -fsSL -o /tmp/tpl.tpz https://github.com/godotengine/godot/releases/download/4.4.1-stable/Godot_v4.4.1-stable_export_templates.tpz && unzip -q -j /tmp/tpl.tpz templates/linux_release.x86_64 templates/linux_debug.x86_64 templates/web_nothreads_release.zip templates/web_nothreads_debug.zip templates/version.txt -d /opt/godot-data/godot/export_templates/4.4.1.stable && rm -f /tmp/tpl.tpz && chmod -R a+rX /opt/godot-data
COPY files/ /task/
COPY inputs/ /task/inputs/
RUN rm -f /task/.keep /task/inputs/.keep && mkdir -p /task/outputs && useradd -m -u 1000 agent && chown -R agent /task
WORKDIR /task
