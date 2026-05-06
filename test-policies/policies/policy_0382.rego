package governance.authentication.user.validate.core.policy_0382

# Auto-generated policy 382 (Rego v1 syntax)
# Package: governance.authentication.user.validate.core

# Metadata
metadata := {
    "policy_id": "0382",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0382_allowed if {
    input.user.role == "admin"
}
policy_0382_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0382_allowed if {
    input.user.active
    input.resource.public
}
