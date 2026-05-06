package access.enforcement.context.validate.policy_0717

# Auto-generated policy 717 (Rego v1 syntax)
# Package: access.enforcement.context.validate

# Metadata
metadata := {
    "policy_id": "0717",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0717_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0717_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0717_allowed if {
    input.user.active
    input.resource.public
}
