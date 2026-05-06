package governance.validation.user.validate.logic.policy_0315

# Auto-generated policy 315 (Rego v1 syntax)
# Package: governance.validation.user.validate.logic

# Metadata
metadata := {
    "policy_id": "0315",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0315_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0315_allowed if {
    input.user.active
    input.resource.public
}
default policy_0315_allowed = false
