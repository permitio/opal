package risk.authorization.context.allow.policy_0387

# Auto-generated policy 387 (Rego v1 syntax)
# Package: risk.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0387",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0387_allowed if {
    input.user.role == "admin"
}
policy_0387_allowed if {
    data.policies.risk.enabled
}
