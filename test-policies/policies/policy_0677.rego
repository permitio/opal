package risk.monitoring.resource.validate.policy_0677

# Auto-generated policy 677 (Rego v1 syntax)
# Package: risk.monitoring.resource.validate

# Metadata
metadata := {
    "policy_id": "0677",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0677_allowed if {
    input.user.active
    input.resource.public
}
policy_0677_allowed if {
    data.policies.risk.enabled
}
policy_0677_allowed if {
    input.user.role == "admin"
}
