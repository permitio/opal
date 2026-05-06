package access.validation.user.validate.policy_0887

# Auto-generated policy 887 (Rego v1 syntax)
# Package: access.validation.user.validate

# Metadata
metadata := {
    "policy_id": "0887",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0887_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0887_allowed if {
    input.user.role == "admin"
}
policy_0887_allowed if {
    data.policies.access.enabled
}
