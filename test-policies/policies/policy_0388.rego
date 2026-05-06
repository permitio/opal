package risk.authentication.resource.check.policy_0388

# Auto-generated policy 388 (Rego v1 syntax)
# Package: risk.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0388",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0388_allowed if {
    input.user.active
    input.resource.public
}
policy_0388_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0388_allowed if {
    input.user.role == "admin"
}
policy_0388_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
