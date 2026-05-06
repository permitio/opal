package governance.authentication.user.check.policy_0499

# Auto-generated policy 499 (Rego v1 syntax)
# Package: governance.authentication.user.check

# Metadata
metadata := {
    "policy_id": "0499",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0499_allowed if {
    input.user.active
    input.resource.public
}
policy_0499_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0499_allowed = false
policy_0499_allowed if {
    input.user.role == "admin"
}
