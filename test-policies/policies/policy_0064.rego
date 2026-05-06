package audit.monitoring.policy.allow.policy_0064

# Auto-generated policy 64 (Rego v1 syntax)
# Package: audit.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0064",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0064_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0064_allowed = false
policy_0064_allowed if {
    data.policies.audit.enabled
}
