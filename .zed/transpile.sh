#!/usr/bin/env bash
# Asks for a Crop2ML package and target(s), then transpiles with this PyCrop2ML checkout.
# usage (from a Zed task): bash transpile.sh <PyCrop2ML root>; run in the directory holding the packages
root=${1:?usage: transpile.sh <PyCrop2ML root>}

run_python() {
    pixi run --manifest-path "$root/pyproject.toml" python "$@"
}

# targets that generate a package (`check` has no file extension: it only validates)
available_targets=$(run_python -c '
from pycropml.transpiler.target_registry import discover_targets
print(" ".join(name for name, target in discover_targets().items() if target.extension))
' 2>/dev/null)
if [ -z "$available_targets" ]; then
    echo "Could not get the list of targets from PyCrop2ML in $root"
    exit 1
fi
available_packages=$(ls -d */crop2ml 2>/dev/null | cut -d/ -f1 | tr '\n' ' ')

# true if $1 is a Crop2ML package (plain glob: compgen is missing in non-interactive bash builds)
is_package() {
    local f
    for f in "$1"/crop2ml/composition*.xml; do
        [ -n "$1" ] && [ -e "$f" ] && return 0
    done
    return 1
}

# true if every word of $1 is an available target
are_targets() {
    local t
    [ -n "$1" ] || return 1
    for t in $1; do
        [[ " $available_targets " == *" $t "* ]] || return 1
    done
    return 0
}

# discard input that arrived before the prompts (e.g. the Enter that started the task)
while read -r -t 0.3 _; do :; done

echo "Packages: $available_packages"
read -r -p 'Package: ' pkg
while ! is_package "$pkg"; do
    echo "No Crop2ML package: '$pkg'"
    read -r -p 'Package: ' pkg
done

echo "Targets: $available_targets"
read -r -p 'Target(s) (several separated by spaces, or all): ' targets
[ "$targets" = all ] && targets=$available_targets
while ! are_targets "$targets"; do
    echo "Unknown target in '$targets'"
    read -r -p 'Target(s) (several separated by spaces, or all): ' targets
    [ "$targets" = all ] && targets=$available_targets
done

# one run per target, so that one failing target doesn't stop the others
failed=()
for target in $targets; do
    echo "=== cyml -p $pkg $target"
    run_python "$root/src/pycropml/main.py" -p "$pkg" "$target" || failed+=("$target")
done

if [ ${#failed[@]} -gt 0 ]; then
    echo "=== failed: ${failed[*]}"
    exit 1
fi
echo "=== done: $targets"
