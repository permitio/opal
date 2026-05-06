package access.authorization.action.deny.policy_0742

# Auto-generated policy 742 (Rego v1 syntax)
# Package: access.authorization.action.deny

# Metadata
metadata := {
    "policy_id": "0742",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0742_allowed if {
    input.user.role == "admin"
}
policy_0742_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0742_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0742_allowed if {
    input.user.active
    input.resource.public
}
