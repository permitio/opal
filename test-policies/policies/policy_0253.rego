package audit.monitoring.resource.deny.data.policy_0253

# Auto-generated policy 253 (Rego v1 syntax)
# Package: audit.monitoring.resource.deny.data

# Metadata
metadata := {
    "policy_id": "0253",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0253_allowed if {
    data.policies.audit.enabled
}
policy_0253_allowed if {
    input.user.role == "admin"
}
