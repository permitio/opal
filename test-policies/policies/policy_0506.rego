package compliance.authorization.user.verify.helpers.policy_0506

# Auto-generated policy 506 (Rego v1 syntax)
# Package: compliance.authorization.user.verify.helpers

# Metadata
metadata := {
    "policy_id": "0506",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0506_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0506_allowed if {
    input.user.role == "admin"
}
policy_0506_allowed if {
    input.user.active
    input.resource.public
}
