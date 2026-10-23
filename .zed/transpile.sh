#!/usr/bin/env bash
# Asks for a Crop2ML package and target(s), then transpiles with this PyCrop2ML checkout.
# usage (from a Zed task): bash transpile.sh <PyCrop2ML root>; run in the directory holding the packages
root=${1:?usage: transpile.sh <PyCrop2ML root>}

# discard input that arrived before the prompt (e.g. the Enter that started the task)
while read -r -t 0.3 _; do :; done

# true if $1 is a Crop2ML package (plain glob: compgen is missing in non-interactive bash builds)
is_package() {
    local f
    for f in "$1"/crop2ml/composition*.xml; do
        [ -n "$1" ] && [ -e "$f" ] && return 0
    done
    return 1
}

available=$(ls -d */crop2ml 2>/dev/null | cut -d/ -f1 | tr '\n' ' ')
read -r -p 'Package: ' pkg
while ! is_package "$pkg"; do
    echo "No Crop2ML package: '$pkg'. Available: $available"
    read -r -p 'Package: ' pkg
done
read -r -p 'Target(s) [cpp2]: ' targets
targets=${targets:-cpp2}

echo "cyml -p $pkg $targets"
# $targets unquoted on purpose: several targets separated by spaces
pixi run --manifest-path "$root/pyproject.toml" python "$root/src/pycropml/main.py" -p "$pkg" $targets
