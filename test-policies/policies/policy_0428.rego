package compliance.authentication.user.validate.logic.policy_0428

# Auto-generated policy 428 (Rego v1 syntax)
# Package: compliance.authentication.user.validate.logic

# Metadata
metadata := {
    "policy_id": "0428",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0428_allowed = false
policy_0428_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0428_allowed if {
    input.user.active
    input.resource.public
}
