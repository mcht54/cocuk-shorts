#!/usr/bin/env bash
# Blender'ı (önbellekte yoksa) resmî site ya da yansılarından indirir, SHA-256 ile doğrular.
# Bir kaynak kapanırsa sıradaki denenir.
set -euo pipefail
SURUM=5.2.3
SHA=78486c018b4443efe5e75ab54c290ed8c15abafd249b862c2c9ce2530a918eec
[ -x blender/blender ] && exit 0
for KAYNAK in https://download.blender.org/release https://mirrors.dotsrc.org/blender/blender-release \
              https://ftp.halifax.rwth-aachen.de/blender/release https://mirror.clarkson.edu/blender/release; do
  echo "indiriliyor: $KAYNAK"
  if curl -sfL --retry 3 -o blender.tar.xz "$KAYNAK/Blender5.2/blender-$SURUM-linux-x64.tar.xz" \
     && echo "$SHA  blender.tar.xz" | sha256sum -c --quiet; then
    tar -xJf blender.tar.xz && mv "blender-$SURUM-linux-x64" blender && rm blender.tar.xz
    exit 0
  fi
done
echo "Blender hiçbir kaynaktan indirilemedi" >&2
exit 1
