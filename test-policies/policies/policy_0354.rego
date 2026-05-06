package governance.enforcement.context.validate.policy_0354

# Auto-generated policy 354 (Rego v1 syntax)
# Package: governance.enforcement.context.validate

# Metadata
metadata := {
    "policy_id": "0354",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0354_allowed if {
    input.user.role == "admin"
}
policy_0354_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0354_allowed = false
