package security.validation.resource.check.policy_0638

# Auto-generated policy 638 (Rego v1 syntax)
# Package: security.validation.resource.check

# Metadata
metadata := {
    "policy_id": "0638",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0638_allowed if {
    data.policies.security.enabled
}
policy_0638_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0638_allowed if {
    input.user.active
    input.resource.public
}
