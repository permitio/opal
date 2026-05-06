package risk.validation.user.check.logic.policy_0862

# Auto-generated policy 862 (Rego v1 syntax)
# Package: risk.validation.user.check.logic

# Metadata
metadata := {
    "policy_id": "0862",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0862_allowed if {
    data.policies.risk.enabled
}
policy_0862_allowed if {
    input.user.active
    input.resource.public
}
