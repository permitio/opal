package security.enforcement.action.check.policy_0780

# Auto-generated policy 780 (Rego v1 syntax)
# Package: security.enforcement.action.check

# Metadata
metadata := {
    "policy_id": "0780",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0780_allowed if {
    input.user.active
    input.resource.public
}
policy_0780_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0780_allowed if {
    input.user.role == "admin"
}
