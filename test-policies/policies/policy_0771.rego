package audit.monitoring.policy.validate.helpers.policy_0771

# Auto-generated policy 771 (Rego v1 syntax)
# Package: audit.monitoring.policy.validate.helpers

# Metadata
metadata := {
    "policy_id": "0771",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0771_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0771_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0771_allowed if {
    input.user.active
    input.resource.public
}
policy_0771_allowed if {
    input.user.role == "admin"
}
