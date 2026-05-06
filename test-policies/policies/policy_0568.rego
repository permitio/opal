package audit.enforcement.resource.deny.policy_0568

# Auto-generated policy 568 (Rego v1 syntax)
# Package: audit.enforcement.resource.deny

# Metadata
metadata := {
    "policy_id": "0568",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0568_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0568_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
