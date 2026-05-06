package risk.monitoring.policy.check.data.policy_0035

# Auto-generated policy 35 (Rego v1 syntax)
# Package: risk.monitoring.policy.check.data

# Metadata
metadata := {
    "policy_id": "0035",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0035_allowed if {
    data.policies.risk.enabled
}
policy_0035_allowed if {
    input.user.role == "admin"
}
policy_0035_allowed if {
    input.user.active
    input.resource.public
}
