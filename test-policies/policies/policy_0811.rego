package governance.authorization.action.verify.policy_0811

# Auto-generated policy 811 (Rego v1 syntax)
# Package: governance.authorization.action.verify

# Metadata
metadata := {
    "policy_id": "0811",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0811_allowed if {
    input.user.active
    input.resource.public
}
policy_0811_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0811_allowed = false
policy_0811_allowed if {
    input.user.role == "admin"
}
