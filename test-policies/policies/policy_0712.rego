package audit.authorization.context.check.helpers.policy_0712

# Auto-generated policy 712 (Rego v1 syntax)
# Package: audit.authorization.context.check.helpers

# Metadata
metadata := {
    "policy_id": "0712",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0712_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0712_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0712_allowed if {
    data.policies.audit.enabled
}
policy_0712_allowed if {
    input.user.active
    input.resource.public
}
