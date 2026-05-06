package risk.monitoring.policy.allow.policy_0007

# Auto-generated policy 7 (Rego v1 syntax)
# Package: risk.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0007",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0007_allowed if {
    input.user.active
    input.resource.public
}
policy_0007_allowed if {
    input.user.role == "admin"
}
policy_0007_allowed if {
    data.policies.risk.enabled
}
