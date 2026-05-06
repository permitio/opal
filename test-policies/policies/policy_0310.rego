package governance.authentication.resource.verify.helpers.policy_0310

# Auto-generated policy 310 (Rego v1 syntax)
# Package: governance.authentication.resource.verify.helpers

# Metadata
metadata := {
    "policy_id": "0310",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0310_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0310_allowed if {
    input.user.role == "admin"
}
