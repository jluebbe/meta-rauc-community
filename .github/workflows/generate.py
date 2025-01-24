#!/usr/bin/env python3

from jinja2 import Template

TEMPLATE = """
name: build «« layer »»

on:
  push:
    branches:
      - master
    paths:
      - '.github/workflows/«« layer »».yml'
      - '«« layer »»/**'
  pull_request:
    branches:
      - master
    paths:
      - '.github/workflows/«« layer »».yml'
      - '«« layer »»/**'
  # allow rebuilding without a push
  workflow_dispatch: {}

jobs:
  build:
    name: «« layer »» Build
    # run on self-hosted runner for the main repo or if vars.BUILD_RUNS_ON is set
    runs-on: >-
      ${{
        (vars.BUILD_RUNS_ON != ''  && fromJSON(vars.BUILD_RUNS_ON)) ||
        (github.repository == 'rauc/meta-rauc-community' && fromJSON('["self-hosted", "forrest", "build"]')) ||
        'ubuntu-20.04'
      }}
    steps:
      - name: Install required packages
        run: |
          sudo apt-get -q -y --no-install-recommends install diffstat
      - name: Checkout
        uses: actions/checkout@v4
      «% for name, url in base_layers.items()|list + extra_layers.items()|list %»
      - name: Clone «« name »»
        run: git clone --shared --reference-if-able /srv/shared-git/«« name »».git -b master «« url »»
      «% endfor %»
      - name: Initialize build directory
        run: |
          source poky/oe-init-build-env build
          bitbake-layers add-layer ../meta-rauc
          «% for name in extra_layers.keys() %»
          bitbake-layers add-layer ../«« name »»
          «% endfor %»
          bitbake-layers add-layer ../«« layer »»
          if [ -f ~/.yocto/auto.conf ]; then
            cp ~/.yocto/auto.conf conf/
            echo 'SOURCE_MIRROR_URL = "http://10.0.2.2/rauc-community/downloads"' >> conf/auto.conf
          else
            echo 'SSTATE_MIRRORS = "file://.* https://github-runner.pengutronix.de/rauc-community/sstate-cache/PATH"' >> conf/auto.conf
            echo 'BB_SIGNATURE_HANDLER = "OEBasicHash"' >> conf/auto.conf
            echo 'BB_HASHSERVE = ""' >> conf/auto.conf
            echo 'OPKGBUILDCMD = "opkg-build -Z gzip -a -1n"' >> conf/auto.conf
            echo 'INHERIT += "rm_work"' >> conf/auto.conf
          fi
          echo 'DISTRO_FEATURES:remove = "alsa bluetooth usbgadget usbhost wifi nfs zeroconf pci 3g nfc x11 opengl ptest wayland vulkan"' >> conf/local.conf
          «% if machine %»
          echo 'MACHINE = "«« machine »»"' >> conf/local.conf
          «% endif %»
          echo 'DISTRO_FEATURES:append = " rauc"' >> conf/local.conf
          echo 'IMAGE_INSTALL:append = " rauc"' >> conf/local.conf
          echo 'IMAGE_FSTYPES = "«« fstypes »»"' >> conf/local.conf
          echo 'WKS_FILE = "«« wks_file »»"' >> conf/local.conf
          «% for line in conf %»
          echo '«« line »»' >> conf/local.conf
          «% endfor %»
      - name: Show configuration files
        run: |
          cd build/conf
          rgrep . *.conf
      - name: Test bitbake parsing
        run: |
          source poky/oe-init-build-env build
          bitbake -p
      - name: Build rauc, rauc-native
        run: |
          source poky/oe-init-build-env build
          bitbake rauc rauc-native
      - name: Build core-image-minimal
        run: |
          source poky/oe-init-build-env build
          bitbake core-image-minimal --runall=fetch
      - name: Cache Data
        env:
          CACHE_KEY: ${{ secrets.YOCTO_CACHE_KEY }}
        if: ${{ env.CACHE_KEY }}
        run: |
          mkdir -p ~/.ssh
          echo "$CACHE_KEY" >> ~/.ssh/id_ed25519
          chmod 600 ~/.ssh/id_ed25519
          rsync -rvx --ignore-existing build/downloads rauc-community-cache: || true
          rsync -rvx --ignore-existing build/sstate-cache rauc-community-cache: || true
""".lstrip()

template = Template(
        TEMPLATE,
        block_start_string='«%',
        block_end_string='%»',
        variable_start_string='««',
        variable_end_string='»»',
        comment_start_string='«#',
        comment_end_string='#»',
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        )

default_context = {
    "base_layers": {
        "poky": "https://github.com/yoctoproject/poky.git",
        "meta-rauc": "https://github.com/rauc/meta-rauc.git"
    },
    "extra_layers": {
    },
    "machine": None,
    "conf": [],
}

contexts = [
    {
        **default_context,
        "layer": "meta-rauc-qemux86",
        "fstypes": "tar.bz2 wic",
        "wks_file": "qemux86-grub-efi.wks",
        "conf": [
            'EXTRA_IMAGEDEPENDS += "ovmf"',
            'PREFERRED_RPROVIDER_virtual-grub-bootconf = "rauc-qemu-grubconf"',
        ],
    },
    {
        **default_context,
        "layer": "meta-rauc-raspberrypi",
        "extra_layers": {
            "meta-raspberrypi": "https://github.com/agherzan/meta-raspberrypi.git",
        },
        "machine": "raspberrypi4",
        "fstypes": "ext4",
        "wks_file": "sdimage-dual-raspberrypi.wks.in",
    },
]

for context in contexts:
    output = template.render(context)
    file_name = f"{context['layer']}.yml"
    with open(file_name, "w") as file:
        file.write(output)
    print(f"generated {file_name}")
