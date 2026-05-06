package risk.monitoring.policy.allow.policy_0079

# Auto-generated policy 79 (Rego v1 syntax)
# Package: risk.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0079",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0079_allowed = false
policy_0079_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0079_allowed if {
    data.policies.risk.enabled
}
