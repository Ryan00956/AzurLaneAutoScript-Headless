# Third-party notices and distribution boundary

This file records the license boundary of the source repository. It is not a
complete notice bundle for binary artifacts built from external projects.

## Repository license scope

Except where a file or directory carries a different license notice, original
source and documentation in this repository are distributed under the GNU
General Public License, version 3 only (`GPL-3.0-only`), in [LICENSE](LICENSE).
Copyright remains with the respective contributors.

## AzurLaneAutoScript (ALAS)

- Upstream: <https://github.com/LmeSzinc/AzurLaneAutoScript>
- Pinned integration commit: `81ccf63b4540f00241628c82a58c02c7a2bb11af`
- Upstream license: GNU General Public License v3.0
- Local integration surface: `integration/alas/0001-semantic-oracle-hooks.patch`

The integration patch modifies and contains context from GPL-covered ALAS
source. It is distributed under `GPL-3.0-only`. This repository does not
contain a complete ALAS checkout; users obtain ALAS from its upstream project
and apply the pinned patch explicitly.

## ANGLE

- Upstream: <https://chromium.googlesource.com/angle/angle>
- Public mirror: <https://github.com/google/angle>
- Pinned revision: `be80ce591a481c12d60c50d6040d40c035b40a2b`
- License: ANGLE BSD-style three-clause license, reproduced in
  [LICENSES/ANGLE-BSD-3-Clause.txt](LICENSES/ANGLE-BSD-3-Clause.txt)
- Local surfaces: `patches/angle/`, `patches/angle-g3/`, and
  `overlays/angle-g3/`

Those directories contain patches for, or source intended to be placed into,
ANGLE and retain ANGLE's BSD license and copyright notices. The root GPL
license does not replace those file-specific terms.

No built ANGLE APK is tracked or distributed by this source repository. A
future binary distribution must preserve the notices for ANGLE and every
third-party component included in that particular build; this single ANGLE
license file is not a substitute for the complete notice bundle produced from
the pinned checkout.

## Unity

`unity/HeadlessContract/` contains project source and configuration, but does
not contain the Unity Editor or Unity package source/binaries. Unity software
and built-in packages are obtained separately and remain governed by Unity's
applicable engine, package, and companion-license terms. The repository's GPL
license does not relicense Unity software.

## Android, AOSP/Cuttlefish, QEMU, Gradle, and build tools

Scripts may invoke or download separately obtained Android SDK components,
Chromium depot_tools, AOSP/Cuttlefish images, QEMU/Android Emulator binaries,
Gradle components, or platform toolchains. They are not included in the Git
history of this source repository and remain under their own licenses. If any
of them are later distributed as release assets, their exact source, license,
NOTICE, source-offer, and attribution requirements must be reviewed for that
artifact.

## Azur Lane game, accounts, and trademarks

This repository does not distribute the Azur Lane APK, game resource packs,
account data, images, audio, or proprietary game binaries. Local `artifacts/`
and `evidence/` directories are ignored and are not part of the open-source
distribution. Users must obtain and use the game and any account data under
the terms that apply to them.

Azur Lane and the names and marks of its publishers and developers belong to
their respective owners. This is an unofficial research project and is not
affiliated with or endorsed by the Azur Lane rights holders, ALAS maintainers,
Google/ANGLE, or Unity.

## Release-asset gate

Do not attach APKs, Android images, toolchains, game resources, userdata, or
captured account evidence to a public release merely because the source tree
is publishable. Every binary release needs an artifact-specific provenance and
license review, complete third-party notices, required corresponding source or
source offer, integrity hashes, and a privacy check.
