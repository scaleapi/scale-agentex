#!/bin/bash
#
# Pull error logs from a deployment since 6am today
#
# Usage: ./pull-error-logs.sh <deployment-name> [namespace] [output-file]
#   deployment-name - Name of the deployment to fetch logs for (required)
#   namespace       - Kubernetes namespace (default: auto-detect or 'default')
#   output-file     - Optional file to save logs (default: stdout)

set -euo pipefail

DEPLOYMENT_NAME="${1:-}"
NAMESPACE="${2:-}"
OUTPUT_FILE="${3:-}"

if [[ -z "$DEPLOYMENT_NAME" ]]; then
    echo "Error: deployment name is required" >&2
    echo "Usage: $0 <deployment-name> [namespace] [output-file]" >&2
    exit 1
fi

# Calculate hours since 6am today
calculate_since_6am() {
    local now_epoch current_hour current_min today_6am_epoch hours_since

    now_epoch=$(date +%s)
    current_hour=$(date +%H)
    current_min=$(date +%M)

    # Get today's 6am in epoch
    today_6am_epoch=$(date -v6H -v0M -v0S +%s 2>/dev/null || date -d "today 15:00:00" +%s)

    # If it's before 6am, use yesterday's 6am
    if [[ $now_epoch -lt $today_6am_epoch ]]; then
        today_6am_epoch=$(date -v-1d -v6H -v0M -v0S +%s 2>/dev/null || date -d "yesterday 06:00:00" +%s)
    fi

    hours_since=$(( (now_epoch - today_6am_epoch) / 3600 + 1 ))
    echo "${hours_since}h"
}

# Auto-detect namespace if not provided
detect_namespace() {
    local ns deployment_name="$1"

    # Try common namespace patterns for the deployment
    for ns in "$deployment_name" "${deployment_name}-prod" "${deployment_name}-staging" default; do
        if kubectl get namespace "$ns" &>/dev/null; then
            if kubectl get deployment -n "$ns" 2>/dev/null | grep -q "$deployment_name"; then
                echo "$ns"
                return
            fi
        fi
    done

    # Fallback: search all namespaces
    ns=$(kubectl get deployments --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{"\n"}{end}' 2>/dev/null | grep "$deployment_name" | head -1 | awk '{print $1}')

    if [[ -n "$ns" ]]; then
        echo "$ns"
    else
        echo "default"
    fi
}

# Main
main() {
    local since namespace pods pod log_output

    since=$(calculate_since_6am)
    echo "Fetching logs for '$DEPLOYMENT_NAME' since 6am today (--since=$since)" >&2

    # Determine namespace
    if [[ -z "$NAMESPACE" ]]; then
        namespace=$(detect_namespace "$DEPLOYMENT_NAME")
        echo "Auto-detected namespace: $namespace" >&2
    else
        namespace="$NAMESPACE"
    fi

    echo "Using namespace: $namespace" >&2

    # Get all deployment-related pods
    pods=$(kubectl get pods -n "$namespace" -o name 2>/dev/null | grep -E "${DEPLOYMENT_NAME}|api|worker|temporal" || true)

    if [[ -z "$pods" ]]; then
        echo "No $DEPLOYMENT_NAME pods found in namespace '$namespace'" >&2
        echo "Available pods:" >&2
        kubectl get pods -n "$namespace" -o name 2>/dev/null | head -10 >&2
        exit 1
    fi

    echo "Found pods:" >&2
    echo "$pods" >&2
    echo "---" >&2

    # Collect error logs
    log_output=""

    for pod in $pods; do
        pod_name=$(basename "$pod")
        echo "Fetching logs from $pod_name..." >&2

        # Get logs and filter for errors (case-insensitive)
        # Common patterns: ERROR, Error, error, CRITICAL, FATAL, Exception, Traceback
        pod_logs=$(kubectl logs "$pod" -n "$namespace" --since="$since" --timestamps 2>/dev/null | \
            grep -v '200 OK' | \
            grep -iE '(2026|error|exception|timeout|traceback|critical|fatal|failed|panic)' || true)

        if [[ -n "$pod_logs" ]]; then
            log_output+="
================================================================================
POD: $pod_name
================================================================================
$pod_logs
"
        fi
    done

    if [[ -z "$log_output" ]]; then
        echo "No error logs found since 6am today." >&2
        exit 0
    fi

    # Output results
    if [[ -n "$OUTPUT_FILE" ]]; then
        echo "$log_output" > "$OUTPUT_FILE"
        echo "Logs saved to: $OUTPUT_FILE" >&2
    else
        echo "$log_output"
    fi
}

main
