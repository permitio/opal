package access.monitoring.action.check.policy_0164

# Auto-generated policy 164 (Rego v1 syntax)
# Package: access.monitoring.action.check

# Metadata
metadata := {
    "policy_id": "0164",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0164_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0164_allowed if {
    input.user.role == "admin"
}
policy_0164_allowed if {
    input.user.active
    input.resource.public
}
