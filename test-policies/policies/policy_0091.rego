package risk.monitoring.user.deny.policy_0091

# Auto-generated policy 91 (Rego v1 syntax)
# Package: risk.monitoring.user.deny

# Metadata
metadata := {
    "policy_id": "0091",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0091_allowed if {
    input.user.active
    input.resource.public
}
policy_0091_allowed if {
    data.policies.risk.enabled
}
