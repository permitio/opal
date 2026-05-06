package governance.monitoring.context.validate.policy_0608

# Auto-generated policy 608 (Rego v1 syntax)
# Package: governance.monitoring.context.validate

# Metadata
metadata := {
    "policy_id": "0608",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0608_allowed if {
    input.user.active
    input.resource.public
}
policy_0608_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0608_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
