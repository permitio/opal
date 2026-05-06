package security.authorization.resource.allow.policy_0551

# Auto-generated policy 551 (Rego v1 syntax)
# Package: security.authorization.resource.allow

# Metadata
metadata := {
    "policy_id": "0551",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0551_allowed if {
    input.user.role == "admin"
}
policy_0551_allowed if {
    input.user.active
    input.resource.public
}
