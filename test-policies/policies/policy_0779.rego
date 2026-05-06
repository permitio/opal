package governance.authorization.user.allow.policy_0779

# Auto-generated policy 779 (Rego v1 syntax)
# Package: governance.authorization.user.allow

# Metadata
metadata := {
    "policy_id": "0779",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0779_allowed = false
policy_0779_allowed if {
    input.user.active
    input.resource.public
}
policy_0779_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0779_allowed if {
    input.user.role == "admin"
}
