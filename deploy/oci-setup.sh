#!/usr/bin/env bash
# oci-setup.sh. Create one Always Free Oracle VM for Job Scout, from your own PC.
#
#   bash deploy/oci-setup.sh                     # dry run: checks everything, creates nothing
#   bash deploy/oci-setup.sh --yes               # creates the network, the key and the VM
#   bash deploy/oci-setup.sh --shape=a1 --yes    # the larger ARM VM, sized to the free limit
#
# Needs the OCI CLI already working on this PC: `oci os ns get` must print a
# namespace. If it does not, run `oci setup config` (API key) or
# `oci session authenticate` (browser login, short-lived), then try again.
#
# Shapes (--shape=auto|micro|a1, default auto):
#   micro  VM.Standard.E2.1.Micro, x86-64, 1 GB RAM. Two are free. Adds 2 GB of swap.
#          Runs everything, including the JobIndex source (Chromium).
#   a1     VM.Standard.A1.Flex, ARM64, sized to what is left of the free ARM
#          allowance, read from OCI at creation time (2 cores and 12 GB on the
#          account this was written against). No Chromium build for ARM, so the
#          JobIndex source cannot run there. Creation can fail with "Out of host
#          capacity" for hours or days; then retry later or use micro.
#   auto   micro if a micro slot is free, else a1 if free ARM allowance is left,
#          else refuse.
#
# It creates only what the Always Free tier covers:
#   - one VCN, one public subnet, one internet gateway, one route table and
#     one security list that opens SSH (port 22) and nothing else inbound
#   - one VM running Ubuntu 24.04
#   - one SSH key pair at ~/.ssh/job_scout_oci
#
# It refuses, and exits 2 before creating anything, when:
#   - the chosen shape has no free allowance left
#   - an instance named job-scout already exists
#
# Exit codes: 0 done (or dry run passed), 1 a check or an OCI call failed,
# 2 refused by a safety check.

set -euo pipefail

PROFILE="${OCI_PROFILE:-DEFAULT}"
NAME="${JOB_SCOUT_VM_NAME:-job-scout}"
KEY="$HOME/.ssh/job_scout_oci"
CONFIG="${OCI_CLI_CONFIG_FILE:-$HOME/.oci/config}"
CREATE=0
CHOICE="auto"

for arg in "$@"; do
    case "$arg" in
        --yes) CREATE=1 ;;
        --shape=*) CHOICE="${arg#--shape=}" ;;
        --profile=*) PROFILE="${arg#--profile=}" ;;
        -h|--help) sed -n '2,31p' "$0"; exit 0 ;;
        *) echo "Unknown option: $arg. Use --yes, --shape=auto|micro|a1, --profile=NAME or --help." >&2; exit 1 ;;
    esac
done

case "$CHOICE" in
    auto|micro|a1) ;;
    *) echo "Unknown shape '$CHOICE'. Use auto, micro or a1." >&2; exit 1 ;;
esac

say() { echo "  $*"; }
step() { echo; echo "== $*"; }
die() { echo "FAILED: $*" >&2; exit 1; }
refuse() { echo "REFUSED: $*" >&2; exit 2; }

oci_() { oci --profile "$PROFILE" "$@"; }

# Sum the numbers in a JSON array the CLI printed, e.g. [ 2.0, 1.0 ] -> 3.
json_sum() { { grep -oE '[0-9]+(\.[0-9]+)?' || true; } | awk '{ s += $1 } END { print s + 0 }'; }

# 1. The CLI and the profile.
step "1. OCI CLI and profile '$PROFILE'"
command -v oci >/dev/null 2>&1 || die "the oci command is not on your PATH. Install the OCI CLI first: https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm"
[ -f "$CONFIG" ] || die "no OCI config at $CONFIG. Run: oci setup config"
oci_ os ns get --query 'data' --raw-output >/dev/null 2>&1 \
    || die "the profile '$PROFILE' does not work. Run: oci setup config (or oci session authenticate), then try again"
say "signed in"

TENANCY="$(awk -v p="[$PROFILE]" '
    $0 == p { inside = 1; next }
    /^\[/ { inside = 0 }
    inside && $1 ~ /^tenancy/ { sub(/^[^=]*=[ \t]*/, ""); print; exit }' "$CONFIG")"
[ -n "$TENANCY" ] || die "no tenancy line under [$PROFILE] in $CONFIG"

REGION="$(awk -v p="[$PROFILE]" '
    $0 == p { inside = 1; next }
    /^\[/ { inside = 0 }
    inside && $1 ~ /^region/ { sub(/^[^=]*=[ \t]*/, ""); print; exit }' "$CONFIG")"
say "region: ${REGION:-unknown}"

# 2. Free-tier limits, read from OCI now, not assumed. All read-only.
step "2. Free-tier limits"
MICROS="$(oci_ compute instance list --compartment-id "$TENANCY" --all \
    --query "length(data[?shape=='VM.Standard.E2.1.Micro' && \"lifecycle-state\"!='TERMINATED'])" --raw-output)" \
    || die "could not list instances"
MICRO_FREE=$(( MICROS < 2 ? 2 - MICROS : 0 ))
say "micro instances: $MICROS in use, $MICRO_FREE free (limit 2)"

A1_CORES_LIMIT="$(oci_ limits value list --compartment-id "$TENANCY" --service-name compute --all \
    --query "data[?name=='standard-a1-core-count'].value | [0]" --raw-output 2>/dev/null || true)"
A1_MEM_LIMIT="$(oci_ limits value list --compartment-id "$TENANCY" --service-name compute --all \
    --query "data[?name=='standard-a1-memory-count'].value | [0]" --raw-output 2>/dev/null || true)"
A1_CORES_LIMIT="${A1_CORES_LIMIT:-0}"; A1_MEM_LIMIT="${A1_MEM_LIMIT:-0}"
[ "$A1_CORES_LIMIT" != "null" ] || A1_CORES_LIMIT=0
[ "$A1_MEM_LIMIT" != "null" ] || A1_MEM_LIMIT=0

A1_CORES_USED="$(oci_ compute instance list --compartment-id "$TENANCY" --all \
    --query "data[?shape=='VM.Standard.A1.Flex' && \"lifecycle-state\"!='TERMINATED'].\"shape-config\".ocpus" \
    --output json 2>/dev/null | json_sum)"
A1_MEM_USED="$(oci_ compute instance list --compartment-id "$TENANCY" --all \
    --query "data[?shape=='VM.Standard.A1.Flex' && \"lifecycle-state\"!='TERMINATED'].\"shape-config\".\"memory-in-gbs\"" \
    --output json 2>/dev/null | json_sum)"

A1_CORES_FREE="$(awk -v l="$A1_CORES_LIMIT" -v u="$A1_CORES_USED" 'BEGIN { f = int(l - u); print (f > 0 ? f : 0) }')"
A1_MEM_FREE="$(awk -v l="$A1_MEM_LIMIT" -v u="$A1_MEM_USED" 'BEGIN { f = int(l - u); print (f > 0 ? f : 0) }')"
say "ARM (a1) allowance: $A1_CORES_FREE cores and $A1_MEM_FREE GB free of $A1_CORES_LIMIT and $A1_MEM_LIMIT"

# Pick the shape.
if [ "$CHOICE" = "auto" ]; then
    if [ "$MICRO_FREE" -gt 0 ]; then CHOICE="micro"
    elif [ "$A1_CORES_FREE" -gt 0 ] && [ "$A1_MEM_FREE" -gt 0 ]; then CHOICE="a1"
    else refuse "no free allowance: both micro slots are in use and no ARM allowance is left. Free one slot, or use another host (see docs/setup-systemd.md)."
    fi
fi

case "$CHOICE" in
    micro)
        SHAPE="VM.Standard.E2.1.Micro"
        SHAPE_CONFIG=""
        [ "$MICRO_FREE" -gt 0 ] || refuse "no free micro slot. Use --shape=a1 for the ARM VM, or free one slot."
        ;;
    a1)
        SHAPE="VM.Standard.A1.Flex"
        [ "$A1_CORES_FREE" -gt 0 ] && [ "$A1_MEM_FREE" -gt 0 ] || refuse "no ARM allowance left. Free some of it, or use --shape=micro."
        SHAPE_CONFIG="{\"ocpus\":$A1_CORES_FREE,\"memoryInGBs\":$A1_MEM_FREE}"
        ;;
esac
say "shape: $SHAPE${SHAPE_CONFIG:+ with $SHAPE_CONFIG}"

EXISTING="$(oci_ compute instance list --compartment-id "$TENANCY" --all \
    --query "length(data[?\"display-name\"=='$NAME' && \"lifecycle-state\"!='TERMINATED'])" --raw-output)" \
    || die "could not list instances"
[ "$EXISTING" -eq 0 ] || refuse "an instance named '$NAME' already exists. Use JOB_SCOUT_VM_NAME=other to pick a new name, or remove the old one first."
say "no instance named '$NAME' yet"

AD="$(oci_ iam availability-domain list --compartment-id "$TENANCY" --query 'data[0].name' --raw-output)" \
    || die "could not list availability domains"
say "availability domain: $AD"

IMAGE="$(oci_ compute image list --compartment-id "$TENANCY" \
    --operating-system "Canonical Ubuntu" --operating-system-version "24.04" \
    --shape "$SHAPE" --sort-by TIMECREATED --sort-order DESC \
    --query 'data[0].id' --raw-output)" || die "could not find an Ubuntu 24.04 image"
[ -n "$IMAGE" ] && [ "$IMAGE" != "null" ] || die "no Ubuntu 24.04 image for $SHAPE in this region"
say "image: Ubuntu 24.04 found"

echo
if [ "$CREATE" -eq 0 ]; then
    echo "DRY RUN passed. Everything above is in order."
    echo "Nothing was created. To create the VM, run: bash deploy/oci-setup.sh --yes"
    exit 0
fi

# 3. Create. Only reached with --yes.
step "3. Network (free)"
VCN_ID="$(oci_ network vcn list --compartment-id "$TENANCY" --display-name "$NAME-vcn" \
    --query 'data[0].id' --raw-output 2>/dev/null || true)"
if [ -z "$VCN_ID" ] || [ "$VCN_ID" = "null" ]; then
    VCN_ID="$(oci_ network vcn create --compartment-id "$TENANCY" --display-name "$NAME-vcn" \
        --cidr-block 10.0.0.0/16 --wait-for-state AVAILABLE --query 'data.id' --raw-output)"
    say "created VCN"
else
    say "reusing VCN $NAME-vcn"
fi

IGW_ID="$(oci_ network internet-gateway create --compartment-id "$TENANCY" --vcn-id "$VCN_ID" \
    --display-name "$NAME-igw" --is-enabled true --wait-for-state AVAILABLE --query 'data.id' --raw-output)"

RT_ID="$(oci_ network route-table create --compartment-id "$TENANCY" --vcn-id "$VCN_ID" \
    --display-name "$NAME-rt" --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$IGW_ID\"}]" \
    --wait-for-state AVAILABLE --query 'data.id' --raw-output)"

SL_ID="$(oci_ network security-list create --compartment-id "$TENANCY" --vcn-id "$VCN_ID" \
    --display-name "$NAME-sl" \
    --ingress-security-rules '[{"protocol":"6","source":"0.0.0.0/0","isStateless":false,"tcpOptions":{"destinationPortRange":{"min":22,"max":22}}}]' \
    --egress-security-rules '[{"protocol":"all","destination":"0.0.0.0/0","isStateless":false}]' \
    --wait-for-state AVAILABLE --query 'data.id' --raw-output)"

SUBNET_ID="$(oci_ network subnet create --compartment-id "$TENANCY" --vcn-id "$VCN_ID" \
    --display-name "$NAME-subnet" --cidr-block 10.0.0.0/24 --route-table-id "$RT_ID" \
    --security-list-ids "[\"$SL_ID\"]" --wait-for-state AVAILABLE --query 'data.id' --raw-output)"
say "subnet ready: SSH only, inbound"

step "4. SSH key"
if [ -f "$KEY" ]; then
    say "reusing $KEY"
else
    ssh-keygen -t ed25519 -N "" -C "$NAME" -f "$KEY" >/dev/null
    say "created $KEY"
fi
chmod 600 "$KEY"

step "5. Instance"
CLOUD_INIT="$(mktemp)"
trap 'rm -f "$CLOUD_INIT"' EXIT
if [ "$CHOICE" = "micro" ]; then
    # 1 GB of RAM: add swap so a browser-based source does not run out of memory.
    cat > "$CLOUD_INIT" <<'EOF'
#cloud-config
runcmd:
  - fallocate -l 2G /swapfile
  - chmod 600 /swapfile
  - mkswap /swapfile
  - swapon /swapfile
  - echo '/swapfile none swap sw 0 0' >> /etc/fstab
EOF
else
    printf '#cloud-config\n' > "$CLOUD_INIT"
fi

LAUNCH_ARGS=(--compartment-id "$TENANCY" --availability-domain "$AD" --shape "$SHAPE"
    --image-id "$IMAGE" --subnet-id "$SUBNET_ID" --display-name "$NAME"
    --assign-public-ip true --ssh-authorized-keys-file "$KEY.pub"
    --user-data-file "$CLOUD_INIT" --wait-for-state RUNNING --query 'data.id' --raw-output)
[ -z "$SHAPE_CONFIG" ] || LAUNCH_ARGS+=(--shape-config "$SHAPE_CONFIG")

INSTANCE_ID="$(oci_ compute instance launch "${LAUNCH_ARGS[@]}")" \
    || die "the instance did not launch. 'Out of host capacity' means the shape is busy in this region: retry later, or use --shape=micro"

IP="$(oci_ compute instance list-vnics --instance-id "$INSTANCE_ID" \
    --query 'data[0]."public-ip"' --raw-output)"

step "6. Done"
say "instance RUNNING ($SHAPE), public IP: $IP"
echo
echo "Next, on the VM:"
echo "  ssh -i $KEY ubuntu@$IP"
echo "  sudo apt-get update && sudo apt-get install -y git python3-venv rsync"
echo "  git clone https://github.com/0xarmingithub/job-scout.git && cd job-scout"
echo "  sudo bash deploy/install-systemd.sh"
echo "Then add your API key to /opt/job-scout/.env and edit profile.yaml. See docs/setup-systemd.md."
if [ "$CHOICE" = "a1" ]; then
    echo "Note: this ARM VM cannot run the JobIndex source (no Chromium build for ARM). Turn that source off in config.yaml."
fi
