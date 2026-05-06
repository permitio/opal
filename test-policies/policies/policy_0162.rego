package governance.authorization.context.verify.utils.policy_0162

# Auto-generated policy 162 (Rego v1 syntax)
# Package: governance.authorization.context.verify.utils

# Metadata
metadata := {
    "policy_id": "0162",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0162_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0162_allowed if {
    input.user.active
    input.resource.public
}
policy_0162_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0162_allowed = false
