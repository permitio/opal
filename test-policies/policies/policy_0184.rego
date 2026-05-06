package governance.authorization.context.deny.core.policy_0184

# Auto-generated policy 184 (Rego v1 syntax)
# Package: governance.authorization.context.deny.core

# Metadata
metadata := {
    "policy_id": "0184",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0184_allowed if {
    input.user.active
    input.resource.public
}
policy_0184_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0184_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
