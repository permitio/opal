package security.validation.policy.check.helpers.policy_0472

# Auto-generated policy 472 (Rego v1 syntax)
# Package: security.validation.policy.check.helpers

# Metadata
metadata := {
    "policy_id": "0472",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0472_allowed if {
    input.user.active
    input.resource.public
}
policy_0472_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
