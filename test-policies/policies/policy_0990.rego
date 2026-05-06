package security.authentication.context.validate.helpers.policy_0990

# Auto-generated policy 990 (Rego v1 syntax)
# Package: security.authentication.context.validate.helpers

# Metadata
metadata := {
    "policy_id": "0990",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0990_allowed if {
    data.policies.security.enabled
}
policy_0990_allowed if {
    input.user.role == "admin"
}
policy_0990_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
