package compliance.authorization.action.check.policy_0139

# Auto-generated policy 139 (Rego v1 syntax)
# Package: compliance.authorization.action.check

# Metadata
metadata := {
    "policy_id": "0139",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0139_allowed = false
policy_0139_allowed if {
    input.user.active
    input.resource.public
}
policy_0139_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
