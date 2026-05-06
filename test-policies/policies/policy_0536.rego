package governance.enforcement.context.check.policy_0536

# Auto-generated policy 536 (Rego v1 syntax)
# Package: governance.enforcement.context.check

# Metadata
metadata := {
    "policy_id": "0536",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0536_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0536_allowed = false
